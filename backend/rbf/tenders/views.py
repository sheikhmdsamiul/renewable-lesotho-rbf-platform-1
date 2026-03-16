from rest_framework import viewsets, filters, status
from rest_framework.permissions import IsAuthenticated, SAFE_METHODS, BasePermission
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils import timezone
from datetime import date
from django.conf import settings
from django.core.mail import send_mail
from rest_framework.parsers import MultiPartParser, FormParser
from django_filters.rest_framework import DjangoFilterBackend
from django_filters import FilterSet, DateFromToRangeFilter, RangeFilter, CharFilter, ChoiceFilter
from .models import (
    Tender,
    TenderStatus,
    TenderBid,
    BidStatus,
    TenderBidEvaluation,
    EvaluationStatus,
    TenderContract,
    ContractStatus,
)
from .serializers import (
    TenderSerializer,
    TenderBidSerializer,
    TenderListSerializer,
    TenderBidEvaluationSerializer,
    TenderContractSerializer,
)
from rbf.users.models import UserRole, VendorPrequalification, PrequalificationStatus
from rbf.users.models import User
from rbf.projects.models import Project, Milestone, ProjectStatus
from rbf.projects.audit import log_audit
from rbf.notifications.models import Notification, NotificationChannel, NotificationStatus


class IsRbfOfficialOrReadOnly(BasePermission):
    """
    Allows only RBF Officials to perform write actions; others can read.
    """

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return request.user and request.user.is_authenticated
        return (
            request.user
            and request.user.is_authenticated
            and getattr(request.user, 'role', None) in {UserRole.RBF_OFFICIAL, UserRole.ADMIN}
        )


class TenderFilterSet(FilterSet):
    """Advanced filtering for tenders"""
    deadline_range = DateFromToRangeFilter(field_name='deadline')
    budget_range = RangeFilter(field_name='budget')
    department = CharFilter(field_name='department', lookup_expr='icontains')
    technology_types = CharFilter(method='filter_technology_types')
    
    def filter_technology_types(self, queryset, name, value):
        if value:
            return queryset.filter(technology_types__contains=value)
        return queryset
    
    class Meta:
        model = Tender
        fields = ['status', 'category', 'department', 'is_verified', 'procurement_method']


class TenderViewSet(viewsets.ModelViewSet):
    queryset = Tender.objects.all().order_by('-created_at')
    serializer_class = TenderSerializer
    permission_classes = [IsAuthenticated, IsRbfOfficialOrReadOnly]
    parser_classes = [MultiPartParser, FormParser, *viewsets.ModelViewSet.parser_classes]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = TenderFilterSet
    search_fields = ['reference_number', 'name', 'department', 'category']
    ordering_fields = ['created_at', 'deadline', 'published_at', 'verified_at', 'budget']

    WRITE_ROLES = {UserRole.RBF_OFFICIAL, UserRole.ADMIN}

    def get_queryset(self):
        qs = Tender.objects.all().order_by('-created_at')
        user = self.request.user
        if user.role == UserRole.VENDOR:
            is_approved = VendorPrequalification.objects.filter(
                vendor=user,
                status=PrequalificationStatus.APPROVED,
            ).exists()
            if not is_approved:
                return qs.none()
            return qs.filter(status=TenderStatus.PUBLISHED)
        return qs

    def get_serializer_class(self):
        if self.action == 'list':
            return TenderListSerializer
        return TenderSerializer

    def _assert_write_permission(self):
        user = self.request.user
        if getattr(user, 'role', None) not in {UserRole.RBF_OFFICIAL, UserRole.ADMIN}:
            raise PermissionDenied('Only RBF Officials can create or modify tenders.')

    def check_permissions(self, request):
        super().check_permissions(request)
        if request.method not in SAFE_METHODS and getattr(request.user, 'role', None) not in {UserRole.RBF_OFFICIAL, UserRole.ADMIN}:
            self.permission_denied(request, message='Only RBF Officials can create or modify tenders.')

    def create(self, request, *args, **kwargs):
        self._assert_write_permission()
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        self._assert_write_permission()
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        self._assert_write_permission()
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        self._assert_write_permission()
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=['post'])
    def verify(self, request, pk=None):
        self._assert_write_permission()
        tender = self.get_object()

        tender.is_verified = True
        tender.verified_at = timezone.now()
        tender.save(update_fields=['is_verified', 'verified_at', 'updated_at'])
        log_audit(request.user, 'tender_verified', tender, {'reference_number': tender.reference_number})
        return Response(TenderSerializer(tender).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def publish(self, request, pk=None):
        self._assert_write_permission()
        tender = self.get_object()

        if not tender.is_verified:
            return Response({'detail': 'Tender must be verified before publishing.'}, status=status.HTTP_400_BAD_REQUEST)
        if tender.status == TenderStatus.CLOSED:
            return Response({'detail': 'Closed tender cannot be published.'}, status=status.HTTP_400_BAD_REQUEST)

        tender.status = TenderStatus.PUBLISHED
        tender.published_at = timezone.now()
        tender.save(update_fields=['status', 'published_at', 'updated_at'])
        log_audit(request.user, 'tender_published', tender, {'reference_number': tender.reference_number})

        # Always notify all approved (pre-qualified) vendors on publish
        send_email = True
        notify_all = True

        notification_summary = self._notify_vendors_of_publish(tender, send_email, notify_all)
        if not notification_summary.get('recipient_count'):
            return Response(
                {'detail': 'No approved pre-qualified vendors found to notify.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if send_email and (not notification_summary.get('email_enabled') or notification_summary.get('email_error')):
            return Response(
                {'detail': notification_summary.get('email_error') or 'Email is not configured.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        data = TenderSerializer(tender).data
        data['notification_summary'] = notification_summary
        return Response(data, status=status.HTTP_200_OK)

    def _notify_vendors_of_publish(self, tender: Tender, send_email=True, notify_all=True):
        from rbf.users.models import User, VendorPrequalification, PrequalificationStatus

        # Always notify approved (pre-qualified) vendors
        vendors = User.objects.filter(role=UserRole.VENDOR)
        vendors = vendors.filter(prequalifications__status=PrequalificationStatus.APPROVED)

        vendors = vendors.distinct()
        recipient_count = vendors.count()
        vendors = vendors.only('id', 'email', 'full_name', 'username')
        
        notifications = []
        email_subject = f"Tender Published: {tender.name}"
        email_body = (
            f"A new tender has been published.\n\n"
            f"Reference: {tender.reference_number}\n"
            f"Name: {tender.name}\n"
            f"Category: {tender.category}\n"
            f"Deadline: {tender.deadline}\n"
            f"View details: {settings.FRONTEND_URL}/tenders/{tender.id}\n"
        )

        email_enabled = send_email and bool(
            (settings.EMAIL_HOST_USER and settings.EMAIL_HOST_PASSWORD)
            or str(getattr(settings, 'EMAIL_HOST', '')).lower() in {'mailhog', 'localhost'}
        )

        for vendor in vendors:
            notifications.append(
                Notification(
                    recipient_id=str(vendor.id),
                    recipient_name=vendor.full_name or vendor.username or vendor.email,
                    type=NotificationChannel.IN_APP,
                    event='tender_published',
                    title=email_subject,
                    body=email_body,
                    status=NotificationStatus.SENT,
                    linked_entity_id=str(tender.id),
                )
            )

        if notifications:
            Notification.objects.bulk_create(notifications, ignore_conflicts=True)

        email_recipients = []
        email_error = None
        if email_enabled:
            email_recipients = [v.email for v in vendors if v.email]
            if email_recipients:
                try:
                    send_mail(
                        subject=email_subject,
                        message=email_body,
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        recipient_list=email_recipients,
                        fail_silently=False,
                    )
                except Exception as exc:
                    email_error = str(exc)

        return {
            'recipient_count': recipient_count,
            'email_enabled': email_enabled,
            'email_recipient_count': len(email_recipients),
            'email_error': email_error,
        }


    @action(detail=True, methods=['post'])
    def award(self, request, pk=None):
        self._assert_write_permission()
        tender = self.get_object()

        if tender.status not in {TenderStatus.PUBLISHED, TenderStatus.EVALUATION}:
            return Response(
                {'detail': 'Tender can be awarded only from Published or Evaluation state.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        bid_id = str(request.data.get('bid_id') or '').strip()
        if not bid_id:
            return Response(
                {'detail': 'bid_id is required and must reference a submitted bid.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            bid = TenderBid.objects.get(id=bid_id, tender=tender)
        except TenderBid.DoesNotExist:
            return Response(
                {'detail': 'Bid not found for this tender.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if bid.status not in {BidStatus.SUBMITTED, BidStatus.UNDER_REVIEW, BidStatus.ACCEPTED}:
            return Response(
                {'detail': 'Only submitted or under-review bids can be awarded.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not bid.evaluations.filter(status=EvaluationStatus.SCORED, total_score__gte=71).exists():
            return Response(
                {'detail': 'Bid must have a TAC score of at least 71 before it can be awarded.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        awarded_vendor_id = str(request.data.get('awarded_vendor_id') or '').strip()
        awarded_vendor_name = str(request.data.get('awarded_vendor_name') or '').strip()
        if awarded_vendor_id and awarded_vendor_id != bid.vendor_id:
            return Response(
                {'detail': 'awarded_vendor_id must match the selected bid vendor.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if awarded_vendor_name and bid.vendor_name and awarded_vendor_name != bid.vendor_name:
            return Response(
                {'detail': 'awarded_vendor_name must match the selected bid vendor.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        awarded_vendor_id = awarded_vendor_id or bid.vendor_id
        awarded_vendor_name = awarded_vendor_name or bid.vendor_name
        if not awarded_vendor_id and not awarded_vendor_name:
            return Response(
                {'detail': 'awarded_vendor_id or awarded_vendor_name is required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        tender.status = TenderStatus.AWARDED
        tender.awarded_vendor_id = awarded_vendor_id
        tender.awarded_vendor_name = awarded_vendor_name
        tender.awarded_at = timezone.now()
        tender.save(
            update_fields=[
                'status',
                'awarded_vendor_id',
                'awarded_vendor_name',
                'awarded_at',
                'updated_at',
            ]
        )
        if bid.status != BidStatus.ACCEPTED:
            bid.status = BidStatus.ACCEPTED
            bid.reviewed_at = bid.reviewed_at or timezone.now()
            bid.reviewed_by = bid.reviewed_by or (request.user.full_name or request.user.username)
            bid.save(update_fields=['status', 'reviewed_at', 'reviewed_by', 'updated_at'])
        log_audit(
            request.user,
            'tender_awarded',
            tender,
            {
                'reference_number': tender.reference_number,
                'bid_id': bid_id,
                'awarded_vendor_id': awarded_vendor_id,
                'awarded_vendor_name': awarded_vendor_name,
            },
        )

        # Send award notification
        send_email = request.data.get('send_email', True)
        self._notify_award(tender, awarded_vendor_id, awarded_vendor_name, send_email)
        self._ensure_award_contract(tender, bid, awarded_vendor_id)

        return Response(TenderSerializer(tender).data, status=status.HTTP_200_OK)

    def _notify_award(self, tender: Tender, vendor_id: str, vendor_name: str, send_email=True):
        """Send award notification to winning vendor"""
        from rbf.users.models import User

        try:
            vendor = User.objects.get(id=vendor_id)
        except User.DoesNotExist:
            return

        email_subject = f"Tender Award Notification: {tender.name}"
        email_body = (
            f"Congratulations!\n\n"
            f"You have been awarded the tender.\n\n"
            f"Tender: {tender.name} ({tender.reference_number})\n"
            f"Department: {tender.department}\n"
            f"Awarded at: {timezone.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"Please contact {tender.contact_details} for further details.\n"
        )

        email_enabled = send_email and bool(
            (settings.EMAIL_HOST_USER and settings.EMAIL_HOST_PASSWORD)
            or str(getattr(settings, 'EMAIL_HOST', '')).lower() in {'mailhog', 'localhost'}
        )

        # In-app notification
        Notification.objects.create(
            recipient_id=str(vendor.id),
            recipient_name=vendor.full_name or vendor.username or vendor.email,
            type=NotificationChannel.EMAIL if email_enabled else NotificationChannel.IN_APP,
            event='tender_awarded',
            title=email_subject,
            body=email_body,
            status=NotificationStatus.SENT,
            linked_entity_id=str(tender.id),
        )

        # Email notification
        if email_enabled and vendor.email:
            try:
                send_mail(
                    subject=email_subject,
                    message=email_body,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[vendor.email],
                    fail_silently=True,
                )
            except Exception:
                pass

    def _ensure_award_contract(self, tender: Tender, bid: TenderBid, vendor_id: str):
        """Create a generated contract on award if one doesn't exist."""
        existing = TenderContract.objects.filter(tender=tender, vendor_id=vendor_id).first()
        if existing:
            return existing

        try:
            vendor = User.objects.get(id=vendor_id)
        except User.DoesNotExist:
            return None

        reference_number = f"CTR-{tender.reference_number}-{vendor_id}"
        contract = TenderContract.objects.create(
            tender=tender,
            bid=bid,
            vendor_id=vendor_id,
            vendor_name=vendor.full_name or vendor.username,
            vendor_email=vendor.email or '',
            reference_number=reference_number,
            template_name='Performance-Based Agreement',
            status=ContractStatus.GENERATED,
        )
        log_audit(request.user, 'contract_generated', contract, {'tender_id': str(tender.id)})
        Notification.objects.create(
            recipient_id=vendor_id,
            recipient_name=vendor.full_name or vendor.username,
            type=NotificationChannel.IN_APP,
            event='contract_generated',
            title=f'Contract Ready: {tender.reference_number}',
            body=f'A performance-based agreement is ready for signature (Ref: {reference_number}).',
            linked_entity_id=str(tender.id),
        )
        return contract


    @action(detail=True, methods=['post'])
    def close(self, request, pk=None):
        """Close a tender, preventing further bids"""
        self._assert_write_permission()
        tender = self.get_object()
        
        if tender.status == TenderStatus.CLOSED:
            return Response(
                {'detail': 'Tender is already closed.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        tender.status = TenderStatus.CLOSED
        tender.closed_at = timezone.now()
        tender.save(update_fields=['status', 'closed_at', 'updated_at'])
        log_audit(
            request.user,
            'tender_closed',
            tender,
            {'reference_number': tender.reference_number},
        )
        return Response(TenderSerializer(tender).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def verify_security(self, request, pk=None):
        """Verify tender security deposit"""
        self._assert_write_permission()
        tender = self.get_object()
        
        if not tender.tender_security_required:
            return Response(
                {'detail': 'Security deposit not required for this tender.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        tender.security_deposit_verified = True
        tender.security_deposit_verified_at = timezone.now()
        tender.save(update_fields=['security_deposit_verified', 'security_deposit_verified_at', 'updated_at'])
        
        log_audit(
            request.user,
            'tender_security_verified',
            tender,
            {'reference_number': tender.reference_number},
        )
        return Response(TenderSerializer(tender).data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'])
    def security_verification_search(self, request):
        """Search tenders for security verification"""
        self._assert_write_permission()
        
        # Filter by awarded tenders not yet verified
        queryset = Tender.objects.filter(
            status=TenderStatus.AWARDED,
            security_deposit_verified=False
        ).order_by('-awarded_at')
        
        # Apply search filters
        search_key = request.query_params.get('search_key', '')
        if search_key:
            queryset = queryset.filter(
                reference_number__icontains=search_key
            ) | queryset.filter(name__icontains=search_key)
        
        # Apply date range filter
        award_date_from = request.query_params.get('award_date_from')
        award_date_to = request.query_params.get('award_date_to')
        
        if award_date_from:
            queryset = queryset.filter(awarded_at__gte=award_date_from)
        if award_date_to:
            queryset = queryset.filter(awarded_at__lte=award_date_to)
        
        sort_by = request.query_params.get('sort_by', '-awarded_at')
        queryset = queryset.order_by(sort_by)
        
        limit = int(request.query_params.get('limit', 50))
        queryset = queryset[:limit]
        
        serializer = TenderListSerializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class TenderBidViewSet(viewsets.ModelViewSet):
    """ViewSet for managing vendor bids/submissions"""
    queryset = TenderBid.objects.all().order_by('-submitted_at')
    serializer_class = TenderBidSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['tender', 'vendor_id', 'status']
    search_fields = ['vendor_name', 'vendor_email', 'tender__reference_number']
    ordering_fields = ['submitted_at', 'bid_amount']

    def get_queryset(self):
        user = self.request.user
        if user.role == UserRole.VENDOR:
            return TenderBid.objects.filter(vendor_id=str(user.id))
        return TenderBid.objects.all()

    def create(self, request, *args, **kwargs):
        """Submit a bid for a tender"""
        tender_id = request.data.get('tender')
        if not tender_id:
            raise ValidationError({'tender': 'Tender ID is required.'})
        
        try:
            tender = Tender.objects.get(id=tender_id)
        except Tender.DoesNotExist:
            raise ValidationError({'tender': 'Tender not found.'})
        
        if tender.status != TenderStatus.PUBLISHED:
            raise ValidationError({'tender': 'Tender is not open for bidding.'})

        deadline = tender.last_date_submission or tender.deadline
        if deadline and timezone.now() > deadline:
            raise ValidationError({'tender': 'Bidding deadline has passed.'})

        if request.user.role != UserRole.VENDOR:
            raise ValidationError({'detail': 'Only vendors can submit bids.'})

        # Only pre-qualified vendors can submit bids
        if not VendorPrequalification.objects.filter(
            vendor=request.user,
            status=PrequalificationStatus.APPROVED,
        ).exists():
            raise ValidationError({'detail': 'Only pre-qualified vendors can submit bids.'})

        bid_status = request.data.get('status') or BidStatus.DRAFT
        if bid_status not in {BidStatus.DRAFT, BidStatus.SUBMITTED}:
            raise ValidationError({'status': 'Invalid status for bid submission.'})

        latest_version = (
            TenderBid.objects.filter(tender=tender, vendor_id=str(request.user.id))
            .order_by('-version_number')
            .values_list('version_number', flat=True)
            .first()
        )
        next_version = (latest_version or 0) + 1

        request.data['vendor_id'] = str(request.user.id)
        request.data['vendor_name'] = request.user.full_name or request.user.username
        request.data['vendor_email'] = request.user.email
        request.data['version_number'] = next_version
        request.data['status'] = bid_status
        response = super().create(request, *args, **kwargs)
        if response.status_code == status.HTTP_201_CREATED and request.data.get('status') == BidStatus.SUBMITTED:
            bid_id = response.data.get('id')
            try:
                bid = TenderBid.objects.get(id=bid_id)
            except TenderBid.DoesNotExist:
                bid = None
            if bid:
                log_audit(request.user, 'bid_submitted', bid, {'tender_id': str(tender.id), 'version': bid.version_number})
                Notification.objects.create(
                    recipient_id=bid.vendor_id,
                    recipient_name=bid.vendor_name,
                    type=NotificationChannel.IN_APP,
                    event='bid_submitted',
                    title=f'Bid Submitted: {tender.reference_number}',
                    body=f'Your bid was submitted successfully. Ref: {tender.reference_number} • Version {bid.version_number}.',
                    linked_entity_id=str(tender.id),
                )
        return response

    def update(self, request, *args, **kwargs):
        bid = self.get_object()
        if request.user.role != UserRole.VENDOR or bid.vendor_id != str(request.user.id):
            raise PermissionDenied('Only the submitting vendor can update this bid.')
        if bid.status not in {BidStatus.DRAFT, BidStatus.SUBMITTED}:
            raise ValidationError({'detail': 'Only draft or submitted bids can be updated.'})

        deadline = bid.tender.last_date_submission or bid.tender.deadline
        if deadline and timezone.now() > deadline:
            raise ValidationError({'detail': 'Bidding deadline has passed.'})

        submitting = self._is_submitting(bid, request)
        if submitting:
            self._validate_submission_payload(bid, request)

        response = super().update(request, *args, **kwargs)
        if submitting and response.status_code in {status.HTTP_200_OK, status.HTTP_202_ACCEPTED}:
            bid.refresh_from_db()
            bid.submitted_at = timezone.now()
            bid.status = BidStatus.SUBMITTED
            bid.save(update_fields=['submitted_at', 'status', 'updated_at'])
            log_audit(request.user, 'bid_submitted', bid, {'tender_id': str(bid.tender_id), 'version': bid.version_number})
            Notification.objects.create(
                recipient_id=bid.vendor_id,
                recipient_name=bid.vendor_name,
                type=NotificationChannel.IN_APP,
                event='bid_submitted',
                title=f'Bid Submitted: {bid.tender.reference_number}',
                body=f'Your bid was submitted successfully. Ref: {bid.tender.reference_number} • Version {bid.version_number}.',
                linked_entity_id=str(bid.tender.id),
            )
            response.data = TenderBidSerializer(bid, context=self.get_serializer_context()).data
        return response

    def partial_update(self, request, *args, **kwargs):
        bid = self.get_object()
        if request.user.role != UserRole.VENDOR or bid.vendor_id != str(request.user.id):
            raise PermissionDenied('Only the submitting vendor can update this bid.')
        if bid.status not in {BidStatus.DRAFT, BidStatus.SUBMITTED}:
            raise ValidationError({'detail': 'Only draft or submitted bids can be updated.'})

        deadline = bid.tender.last_date_submission or bid.tender.deadline
        if deadline and timezone.now() > deadline:
            raise ValidationError({'detail': 'Bidding deadline has passed.'})

        submitting = self._is_submitting(bid, request)
        if submitting:
            self._validate_submission_payload(bid, request)

        response = super().partial_update(request, *args, **kwargs)
        if submitting and response.status_code in {status.HTTP_200_OK, status.HTTP_202_ACCEPTED}:
            bid.refresh_from_db()
            bid.submitted_at = timezone.now()
            bid.status = BidStatus.SUBMITTED
            bid.save(update_fields=['submitted_at', 'status', 'updated_at'])
            log_audit(request.user, 'bid_submitted', bid, {'tender_id': str(bid.tender_id), 'version': bid.version_number})
            Notification.objects.create(
                recipient_id=bid.vendor_id,
                recipient_name=bid.vendor_name,
                type=NotificationChannel.IN_APP,
                event='bid_submitted',
                title=f'Bid Submitted: {bid.tender.reference_number}',
                body=f'Your bid was submitted successfully. Ref: {bid.tender.reference_number} • Version {bid.version_number}.',
                linked_entity_id=str(bid.tender.id),
            )
            response.data = TenderBidSerializer(bid, context=self.get_serializer_context()).data
        return response

    def _is_submitting(self, bid: TenderBid, request) -> bool:
        target_status = request.data.get('status')
        return target_status == BidStatus.SUBMITTED and bid.status == BidStatus.DRAFT

    def _validate_submission_payload(self, bid: TenderBid, request):
        deadline = bid.tender.last_date_submission or bid.tender.deadline
        if deadline and timezone.now() > deadline:
            raise ValidationError({'detail': 'Bidding deadline has passed.'})

        stage = request.data.get('stage') or bid.stage
        if stage == "Site-Specific":
            tech_file = request.data.get('technical_proposal_file') or bid.technical_proposal_file
            fin_file = request.data.get('financial_proposal_file') or bid.financial_proposal_file
            boq_file = request.data.get('boq_file') or bid.boq_file
            if not tech_file or not fin_file:
                raise ValidationError({'detail': 'Technical and financial proposal files are required for site-specific bids.'})
            if not boq_file:
                raise ValidationError({'detail': 'BOQ file is required for site-specific bids.'})

    @action(detail=True, methods=['post'])
    def review(self, request, pk=None):
        """Mark bid as under review"""
        bid = self.get_object()
        
        if bid.status != BidStatus.SUBMITTED:
            return Response(
                {'detail': 'Only submitted bids can be reviewed.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        bid.status = BidStatus.UNDER_REVIEW
        bid.reviewed_at = timezone.now()
        bid.reviewed_by = f"{request.user.full_name or request.user.username}"
        bid.save(update_fields=['status', 'reviewed_at', 'reviewed_by'])
        if bid.tender.status == TenderStatus.PUBLISHED:
            deadline = bid.tender.last_date_submission or bid.tender.deadline
            if deadline and timezone.now() > deadline:
                bid.tender.status = TenderStatus.EVALUATION
                bid.tender.save(update_fields=['status', 'updated_at'])
        log_audit(request.user, 'bid_under_review', bid, {'tender_id': str(bid.tender_id)})
        
        return Response(TenderBidSerializer(bid).data, status=status.HTTP_200_OK)


class TenderBidEvaluationViewSet(viewsets.ModelViewSet):
    queryset = TenderBidEvaluation.objects.select_related('bid', 'evaluator').all().order_by('-created_at')
    serializer_class = TenderBidEvaluationSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['bid', 'status']
    search_fields = ['bid__vendor_name', 'bid__tender__reference_number']
    ordering_fields = ['created_at', 'total_score']

    def get_queryset(self):
        user = self.request.user
        qs = TenderBidEvaluation.objects.select_related('bid', 'evaluator')
        if user.role == UserRole.VENDOR:
            return qs.filter(bid__vendor_id=str(user.id))
        return qs

    def _assert_eval_permission(self, request):
        if request.user.role not in {UserRole.RBF_OFFICIAL, UserRole.ADMIN, UserRole.TAC}:
            raise PermissionDenied('Only RBF Officials or TAC members can score bids.')

    def create(self, request, *args, **kwargs):
        self._assert_eval_permission(request)
        data = request.data.copy()
        data['evaluator'] = request.user.id
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        evaluation = serializer.instance
        log_audit(request.user, 'bid_evaluated', evaluation, {'bid_id': str(evaluation.bid_id), 'score': evaluation.total_score})
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        self._assert_eval_permission(request)
        return super().update(request, *args, **kwargs)


class TenderContractViewSet(viewsets.ModelViewSet):
    queryset = TenderContract.objects.select_related('tender', 'bid').all().order_by('-generated_at')
    serializer_class = TenderContractSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['tender', 'status', 'vendor_id']
    search_fields = ['reference_number', 'vendor_name', 'tender__reference_number']
    ordering_fields = ['generated_at']
    parser_classes = [MultiPartParser, FormParser, *viewsets.ModelViewSet.parser_classes]

    def get_queryset(self):
        user = self.request.user
        qs = TenderContract.objects.select_related('tender', 'bid')
        if user.role == UserRole.VENDOR:
            return qs.filter(vendor_id=str(user.id))
        return qs

    def _assert_admin_permission(self, request):
        if request.user.role not in {UserRole.RBF_OFFICIAL, UserRole.ADMIN}:
            raise PermissionDenied('Only RBF Officials or Admins can manage contracts.')

    @action(detail=False, methods=['post'])
    def generate(self, request):
        self._assert_admin_permission(request)
        tender_id = request.data.get('tender')
        bid_id = request.data.get('bid')
        if not tender_id:
            raise ValidationError({'tender': 'Tender ID is required.'})
        try:
            tender = Tender.objects.get(id=tender_id)
        except Tender.DoesNotExist:
            raise ValidationError({'tender': 'Tender not found.'})
        if tender.status != TenderStatus.AWARDED:
            raise ValidationError({'tender': 'Tender must be awarded before generating a contract.'})

        bid = None
        if bid_id:
            try:
                bid = TenderBid.objects.get(id=bid_id, tender=tender)
            except TenderBid.DoesNotExist:
                raise ValidationError({'bid': 'Bid not found for this tender.'})

        vendor_id = str(request.data.get('vendor_id') or (bid.vendor_id if bid else tender.awarded_vendor_id))
        if not vendor_id:
            raise ValidationError({'vendor_id': 'Vendor ID is required.'})
        if tender.awarded_vendor_id and vendor_id != str(tender.awarded_vendor_id):
            raise ValidationError({'vendor_id': 'Vendor must match the awarded vendor for this tender.'})
        if bid and vendor_id != str(bid.vendor_id):
            raise ValidationError({'vendor_id': 'Vendor must match the selected bid vendor.'})
        try:
            vendor = User.objects.get(id=vendor_id)
        except User.DoesNotExist:
            raise ValidationError({'vendor_id': 'Vendor not found.'})

        existing = TenderContract.objects.filter(tender=tender, vendor_id=vendor_id).first()
        if existing:
            return Response(TenderContractSerializer(existing).data, status=status.HTTP_200_OK)

        reference_number = f"CTR-{tender.reference_number}-{vendor_id}"
        contract = TenderContract.objects.create(
            tender=tender,
            bid=bid,
            vendor_id=vendor_id,
            vendor_name=vendor.full_name or vendor.username,
            vendor_email=vendor.email or '',
            reference_number=reference_number,
            template_name=str(request.data.get('template_name') or 'Performance-Based Agreement'),
            status=ContractStatus.GENERATED,
        )
        log_audit(request.user, 'contract_generated', contract, {'tender_id': str(tender.id)})
        Notification.objects.create(
            recipient_id=vendor_id,
            recipient_name=vendor.full_name or vendor.username,
            type=NotificationChannel.IN_APP,
            event='contract_generated',
            title=f'Contract Ready: {tender.reference_number}',
            body=f'A performance-based agreement is ready for signature (Ref: {reference_number}).',
            linked_entity_id=str(tender.id),
        )
        return Response(TenderContractSerializer(contract).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def sign(self, request, pk=None):
        contract = self.get_object()
        if request.user.role != UserRole.VENDOR or contract.vendor_id != str(request.user.id):
            raise PermissionDenied('Only the awarded vendor can sign this contract.')
        if contract.tender.awarded_vendor_id and str(contract.tender.awarded_vendor_id) != str(contract.vendor_id):
            raise ValidationError({'detail': 'Only the awarded vendor can sign this contract.'})
        signed_file = request.data.get('signed_file')
        if not signed_file:
            raise ValidationError({'signed_file': 'Signed contract file is required.'})
        contract.signed_file = signed_file
        contract.signed_at = timezone.now()
        contract.status = ContractStatus.SUBMITTED
        contract.save(update_fields=['signed_file', 'signed_at', 'status', 'updated_at'])
        log_audit(request.user, 'contract_signed', contract, {'tender_id': str(contract.tender_id)})
        admins = User.objects.filter(role__in={UserRole.RBF_OFFICIAL, UserRole.ADMIN}).only('id', 'full_name', 'username')
        if admins:
            notifications = []
            for admin in admins:
                notifications.append(
                    Notification(
                        recipient_id=str(admin.id),
                        recipient_name=admin.full_name or admin.username,
                        type=NotificationChannel.IN_APP,
                        event='contract_signed',
                        title=f'Contract Uploaded: {contract.reference_number}',
                        body=f'A signed contract was uploaded by {contract.vendor_name}. Please review and finalize.',
                        status=NotificationStatus.SENT,
                        linked_entity_id=str(contract.tender_id),
                    )
                )
            Notification.objects.bulk_create(notifications, ignore_conflicts=True)
        return Response(TenderContractSerializer(contract).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        self._assert_admin_permission(request)
        contract = self.get_object()
        if not contract.signed_file:
            return Response({'detail': 'Signed contract file is required before approval.'}, status=status.HTTP_400_BAD_REQUEST)
        if contract.status == ContractStatus.GENERATED:
            contract.status = ContractStatus.SUBMITTED
            contract.save(update_fields=['status', 'updated_at'])
        if contract.status not in {ContractStatus.SUBMITTED, ContractStatus.SIGNED}:
            return Response({'detail': 'Contract must be submitted by the vendor before approval.'}, status=status.HTTP_400_BAD_REQUEST)

        tender = contract.tender
        vendor = User.objects.filter(id=contract.vendor_id).first()
        tech_type = tender.technology_types[0] if isinstance(tender.technology_types, list) and tender.technology_types else tender.category
        project_reference = f"PRJ-{tender.reference_number}-{contract.vendor_id}"
        milestone_plan_id = f"MS-{tender.reference_number}-{contract.vendor_id}"

        requested_start = request.data.get('start_date')
        requested_end = request.data.get('end_date')
        start_date = None
        end_date = None
        if isinstance(requested_start, str) and requested_start:
            try:
                start_date = date.fromisoformat(requested_start)
            except ValueError:
                start_date = None
        if isinstance(requested_end, str) and requested_end:
            try:
                end_date = date.fromisoformat(requested_end)
            except ValueError:
                end_date = None
        if not start_date:
            start_date = tender.awarded_at.date() if tender.awarded_at else timezone.now().date()

        project_budget = None
        if contract.bid and contract.bid.bid_amount:
            project_budget = float(contract.bid.bid_amount)
        elif tender.budget:
            project_budget = float(tender.budget)

        approved_prequal = None
        if vendor:
            approved_prequal = VendorPrequalification.objects.filter(
                vendor=vendor,
                status=PrequalificationStatus.APPROVED,
            ).order_by('-submitted_at').first()

        target_installations = 0
        if contract.bid:
            try:
                bid_sites = list(contract.bid.sites.all())
            except Exception:
                bid_sites = []
            if bid_sites:
                target_installations = len(bid_sites)
                units_total = 0
                for site in bid_sites:
                    config = site.system_configuration or {}
                    if isinstance(config, dict):
                        for key in ('units', 'unit_count', 'systems', 'total_units'):
                            if key in config and isinstance(config[key], (int, float)):
                                units_total += int(config[key])
                                break
                if units_total > 0:
                    target_installations = units_total

        project = Project.objects.create(
            tender=tender,
            project_title=tender.name,
            project_reference=project_reference,
            milestone_plan_id=milestone_plan_id,
            vendor_id=contract.vendor_id,
            vendor_name=contract.vendor_name,
            tech_type=tech_type or '',
            region=(vendor.region if vendor else ''),
            district=(vendor.verification_zone if vendor and vendor.verification_zone else (vendor.region if vendor else '')),
            status=ProjectStatus.INSTALLATION,
            contract_file=contract.signed_file,
            start_date=start_date,
            end_date=end_date,
            budget=project_budget,
            target_installations=target_installations,
            target_female_pct=(approved_prequal.female_beneficiary_target if approved_prequal else 50),
            target_vulnerable_pct=(approved_prequal.vulnerable_group_target if approved_prequal else 30),
        )

        milestones = request.data.get('milestones')
        if isinstance(milestones, str):
            try:
                import json
                milestones = json.loads(milestones)
            except Exception:
                milestones = None

        if not milestones:
            base_amount = 0
            if contract.bid and contract.bid.bid_amount:
                base_amount = float(contract.bid.bid_amount)
            elif tender.budget:
                base_amount = float(tender.budget)
            default_milestones = [
                {'name': 'Mobilization', 'percentage': 20},
                {'name': 'Installation', 'percentage': 60},
                {'name': 'Commissioning', 'percentage': 20},
            ]
            milestones = []
            for item in default_milestones:
                milestones.append({
                    'name': item['name'],
                    'percentage': item['percentage'],
                    'amount': round(base_amount * (item['percentage'] / 100), 2) if base_amount else 0,
                })

        for item in milestones:
            Milestone.objects.create(
                project=project,
                name=item.get('name') or 'Milestone',
                percentage=int(item.get('percentage') or 0),
                amount=item.get('amount') or 0,
            )

        contract.status = ContractStatus.APPROVED
        contract.approved_at = timezone.now()
        contract.approved_by = request.user.full_name or request.user.username
        contract.project_id = str(project.id)
        contract.milestone_plan_id = milestone_plan_id
        contract.save(update_fields=['status', 'approved_at', 'approved_by', 'project_id', 'milestone_plan_id', 'updated_at'])

        log_audit(request.user, 'contract_approved', contract, {'project_id': str(project.id)})
        Notification.objects.create(
            recipient_id=contract.vendor_id,
            recipient_name=contract.vendor_name,
            type=NotificationChannel.IN_APP,
            event='contract_approved',
            title=f'Contract Approved: {tender.reference_number}',
            body='Your contract has been approved. Project and milestones are now active.',
            linked_entity_id=str(tender.id),
        )
        return Response(TenderContractSerializer(contract).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        self._assert_admin_permission(request)
        contract = self.get_object()
        reason = str(request.data.get('rejection_reason') or '').strip()
        if not reason:
            raise ValidationError({'rejection_reason': 'Rejection reason is required.'})
        contract.status = ContractStatus.REJECTED
        contract.rejection_reason = reason
        contract.approved_at = timezone.now()
        contract.approved_by = request.user.full_name or request.user.username
        contract.save(update_fields=['status', 'rejection_reason', 'approved_at', 'approved_by', 'updated_at'])
        log_audit(request.user, 'contract_rejected', contract, {'reason': reason})
        Notification.objects.create(
            recipient_id=contract.vendor_id,
            recipient_name=contract.vendor_name,
            type=NotificationChannel.IN_APP,
            event='contract_rejected',
            title=f'Contract Rejected: {contract.tender.reference_number}',
            body=f'Your contract was rejected. Reason: {reason}',
            linked_entity_id=str(contract.tender.id),
        )
        return Response(TenderContractSerializer(contract).data, status=status.HTTP_200_OK)
    @action(detail=True, methods=['post'])
    def submit(self, request, pk=None):
        """Submit a draft bid (final submission)"""
        bid = self.get_object()

        if request.user.role != UserRole.VENDOR or bid.vendor_id != str(request.user.id):
            raise PermissionDenied('Only the submitting vendor can submit this bid.')

        if bid.status != BidStatus.DRAFT:
            return Response(
                {'detail': 'Only draft bids can be submitted.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        deadline = bid.tender.last_date_submission or bid.tender.deadline
        if deadline and timezone.now() > deadline:
            return Response(
                {'detail': 'Bidding deadline has passed.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if bid.stage == "Site-Specific":
            if not bid.technical_proposal_file or not bid.financial_proposal_file:
                return Response(
                    {'detail': 'Technical and financial proposal files are required for site-specific bids.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if not bid.boq_file:
                return Response(
                    {'detail': 'BOQ file is required for site-specific bids.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        bid.status = BidStatus.SUBMITTED
        bid.submitted_at = timezone.now()
        bid.save(update_fields=['status', 'submitted_at', 'updated_at'])
        log_audit(request.user, 'bid_submitted', bid, {'tender_id': str(bid.tender_id), 'version': bid.version_number})
        Notification.objects.create(
            recipient_id=bid.vendor_id,
            recipient_name=bid.vendor_name,
            type=NotificationChannel.IN_APP,
            event='bid_submitted',
            title=f'Bid Submitted: {bid.tender.reference_number}',
            body=f'Your bid was submitted successfully. Ref: {bid.tender.reference_number} • Version {bid.version_number}.',
            linked_entity_id=str(bid.tender.id),
        )

        return Response(TenderBidSerializer(bid).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def accept(self, request, pk=None):
        """Accept a bid"""
        bid = self.get_object()
        
        if bid.status not in {BidStatus.SUBMITTED, BidStatus.UNDER_REVIEW}:
            return Response(
                {'detail': 'Only submitted or under-review bids can be accepted.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        bid.status = BidStatus.ACCEPTED
        bid.reviewed_at = timezone.now()
        bid.reviewed_by = f"{request.user.full_name or request.user.username}"
        bid.save(update_fields=['status', 'reviewed_at', 'reviewed_by'])
        log_audit(request.user, 'bid_accepted', bid, {'tender_id': str(bid.tender_id)})
        
        # Notify bidder
        try:
            from rbf.users.models import User
            vendor = User.objects.get(id=bid.vendor_id)
            Notification.objects.create(
                recipient_id=bid.vendor_id,
                recipient_name=bid.vendor_name,
                type=NotificationChannel.IN_APP,
                event='bid_accepted',
                title=f'Bid Accepted: {bid.tender.reference_number}',
                body=f'Your bid for tender {bid.tender.name} has been accepted.',
                linked_entity_id=str(bid.tender.id),
            )
        except Exception:
            pass
        
        return Response(TenderBidSerializer(bid).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        """Reject a bid with reason"""
        bid = self.get_object()
        
        if bid.status not in {BidStatus.SUBMITTED, BidStatus.UNDER_REVIEW}:
            return Response(
                {'detail': 'Only submitted or under-review bids can be rejected.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        rejection_reason = request.data.get('rejection_reason', '')
        if not rejection_reason:
            raise ValidationError({'rejection_reason': 'Reason for rejection is required.'})
        
        bid.status = BidStatus.REJECTED
        bid.rejection_reason = rejection_reason
        bid.reviewed_at = timezone.now()
        bid.reviewed_by = f"{request.user.full_name or request.user.username}"
        bid.save(update_fields=['status', 'rejection_reason', 'reviewed_at', 'reviewed_by'])
        log_audit(request.user, 'bid_rejected', bid, {'tender_id': str(bid.tender_id), 'reason': rejection_reason})
        
        # Notify bidder
        try:
            Notification.objects.create(
                recipient_id=bid.vendor_id,
                recipient_name=bid.vendor_name,
                type=NotificationChannel.IN_APP,
                event='bid_rejected',
                title=f'Bid Not Accepted: {bid.tender.reference_number}',
                body=f'Your bid for tender {bid.tender.name} was not accepted. Reason: {rejection_reason}',
                linked_entity_id=str(bid.tender.id),
            )
        except Exception:
            pass
        
        return Response(TenderBidSerializer(bid).data, status=status.HTTP_200_OK)
