from rest_framework import viewsets, filters, status
from rest_framework.permissions import IsAuthenticated, SAFE_METHODS, BasePermission
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils import timezone
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
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
from .pba_pdf import generate_contract_pdf
from rbf.users.models import UserRole, VendorPrequalification, PrequalificationStatus
from rbf.users.models import User
from rbf.users.blacklisting import is_vendor_restricted
from rbf.projects.models import Project, Milestone, ProjectStatus, PaymentClaim, PaymentClaimStatus
from rbf.projects.audit import log_audit
from rbf.projects.integrations import push_project_to_prospect
from rbf.notifications.models import Notification, NotificationChannel, NotificationStatus


CONTRACT_ANNEX_SPECS = (
    (
        'annex_a_file',
        'Annex A',
        'Results Framework',
        'Gender Action Plan',
        ('gender_action_plan_file',),
    ),
    (
        'annex_b_file',
        'Annex B',
        'Implementation Schedule',
        'Implementation Plan',
        ('implementation_plan_file',),
    ),
    (
        'annex_c_file',
        'Annex C',
        'Payment Terms',
        'BOQ and Disbursement Table',
        ('financial_proposal_file', 'boq_file'),
    ),
    (
        'annex_d_file',
        'Annex D',
        'Reporting Formats',
        'Standardized System Templates',
        ('reporting_templates_file', 'milestone_payment_schedule_file', 'schedule_file'),
    ),
    (
        'annex_e_file',
        'Annex E',
        'Technical Standards',
        'Technical Proposal',
        ('technical_proposal_file',),
    ),
)


def _resolve_contract_source_file(tender: Tender, bid: TenderBid, source_fields):
    for field_name in source_fields:
        source = bid if bid is not None and hasattr(bid, field_name) else tender
        file_obj = getattr(source, field_name, None)
        if file_obj:
            return file_obj.name
    return None


def _get_contract_bid(contract: TenderContract):
    if contract.bid_id:
        return contract.bid
    return (
        TenderBid.objects.filter(tender=contract.tender, vendor_id=contract.vendor_id)
        .order_by('-version_number', '-submitted_at')
        .first()
    )


def _attach_awarded_bid_annexes(contract: TenderContract, tender: Tender, bid: TenderBid):
    for contract_field, _label, _title, _source_name, source_fields in CONTRACT_ANNEX_SPECS:
        setattr(contract, contract_field, _resolve_contract_source_file(tender, bid, source_fields))


def _missing_contract_annexes(contract: TenderContract):
    bid = _get_contract_bid(contract)
    missing = []
    for contract_field, label, title, _source_name, source_fields in CONTRACT_ANNEX_SPECS:
        if getattr(contract, contract_field) or _resolve_contract_source_file(contract.tender, bid, source_fields):
            continue
        missing.append(f'{label} ({title})')
    return missing


def _hydrate_contract_from_bid(contract: TenderContract):
    bid = _get_contract_bid(contract)
    if not bid:
        return None
    update_fields = []
    if not contract.bid_id:
        contract.bid = bid
        update_fields.append('bid')
    for contract_field, _label, _title, _source_name, source_fields in CONTRACT_ANNEX_SPECS:
        if getattr(contract, contract_field):
            continue
        resolved_name = _resolve_contract_source_file(contract.tender, bid, source_fields)
        if resolved_name:
            setattr(contract, contract_field, resolved_name)
            update_fields.append(contract_field)
    if update_fields:
        update_fields.append('updated_at')
        contract.save(update_fields=update_fields)
    return bid


def _populate_generated_contract_package(contract: TenderContract, tender: Tender, bid: TenderBid, vendor: User):
    _attach_awarded_bid_annexes(contract, tender, bid)
    generate_contract_pdf(contract, tender, bid, vendor)


def _round_score(value) -> float:
    return float(Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _latest_vendor_prequalification(vendor_id: str):
    return (
        VendorPrequalification.objects.filter(
            vendor_id=vendor_id,
            status=PrequalificationStatus.APPROVED,
        )
        .order_by('-submitted_at')
        .first()
    )


def _build_award_ranking(tender: Tender):
    bids = list(
        TenderBid.objects.filter(
            tender=tender,
            status__in={BidStatus.SUBMITTED, BidStatus.UNDER_REVIEW, BidStatus.ACCEPTED, BidStatus.AWARDED},
        )
        .prefetch_related('evaluations')
        .order_by('submitted_at', 'id')
    )
    technical_threshold = tender.technical_threshold or 70
    technical_weight = Decimal(str(tender.technical_weight or 70)) / Decimal("100")
    financial_weight = Decimal(str(tender.financial_weight or 30)) / Decimal("100")

    ranking_rows = []
    qualifying_rows = []

    for bid in bids:
        scored_evaluations = [ev for ev in bid.evaluations.all() if ev.status == EvaluationStatus.SCORED]
        if not scored_evaluations:
            ranking_rows.append({
                'bid_id': str(bid.id),
                'vendor_id': str(bid.vendor_id),
                'vendor_name': bid.vendor_name,
                'bid_amount': float(bid.bid_amount or 0),
                'technical_score': None,
                'financial_score': None,
                'combined_score': None,
                'gender_score': None,
                'female_headed_household_target': 0,
                'passed_technical_threshold': False,
                'financial_opened': False,
                'is_recommended_winner': False,
                'disqualification_reason': 'No scored technical evaluation has been submitted yet.',
            })
            continue

        technical_score = sum(Decimal(str(ev.total_score or 0)) for ev in scored_evaluations) / Decimal(len(scored_evaluations))
        gender_score = sum(Decimal(str(ev.gender_score or 0)) for ev in scored_evaluations) / Decimal(len(scored_evaluations))
        prequal = _latest_vendor_prequalification(str(bid.vendor_id))
        female_target = prequal.female_beneficiary_target if prequal else 0

        row = {
            'bid_id': str(bid.id),
            'vendor_id': str(bid.vendor_id),
            'vendor_name': bid.vendor_name,
            'bid_amount': float(bid.bid_amount or 0),
            'technical_score': _round_score(technical_score),
            'financial_score': None,
            'combined_score': None,
            'gender_score': _round_score(gender_score),
            'female_headed_household_target': female_target,
            'passed_technical_threshold': technical_score >= Decimal(str(technical_threshold)),
            'financial_opened': False,
            'is_recommended_winner': False,
            'disqualification_reason': '',
        }

        if not row['passed_technical_threshold']:
            row['disqualification_reason'] = f'Technical score below threshold ({technical_threshold}%).'
            ranking_rows.append(row)
            continue
        if not bid.bid_amount or Decimal(str(bid.bid_amount or 0)) <= 0:
            row['disqualification_reason'] = 'Financial proposal is missing or invalid.'
            ranking_rows.append(row)
            continue

        qualifying_rows.append((bid, row))

    if qualifying_rows:
        lowest_bid_amount = min(Decimal(str(bid.bid_amount)) for bid, _row in qualifying_rows)
        for bid, row in qualifying_rows:
            vendor_price = Decimal(str(bid.bid_amount))
            financial_score = (lowest_bid_amount / vendor_price) * Decimal("100")
            combined_score = (
                technical_weight * Decimal(str(row['technical_score']))
                + financial_weight * financial_score
            )
            row['financial_opened'] = True
            row['financial_score'] = _round_score(financial_score)
            row['combined_score'] = _round_score(combined_score)
            ranking_rows.append(row)

        ranking_rows.sort(
            key=lambda item: (
                item['combined_score'] is None,
                -(item['combined_score'] or 0),
                -(item['female_headed_household_target'] or 0),
                -(item['gender_score'] or 0),
                item['bid_amount'] or 0,
            )
        )
        recommended_bid_id = next((row['bid_id'] for row in ranking_rows if row['combined_score'] is not None), None)
        for index, row in enumerate(ranking_rows, start=1):
            row['rank'] = index
            row['is_recommended_winner'] = row['bid_id'] == recommended_bid_id
    else:
        for index, row in enumerate(ranking_rows, start=1):
            row['rank'] = index

    recommended_row = next((row for row in ranking_rows if row.get('is_recommended_winner')), None)
    return {
        'technical_weight': tender.technical_weight,
        'financial_weight': tender.financial_weight,
        'technical_threshold': technical_threshold,
        'cooling_off_days': tender.cooling_off_days,
        'rows': ranking_rows,
        'recommended': recommended_row,
    }


def _notify_intent_to_award(tender: Tender, ranking_payload: dict, send_email=True):
    recommended = ranking_payload.get('recommended')
    if not recommended:
        return

    bids_by_vendor = {row['vendor_id']: row for row in ranking_payload.get('rows', [])}
    cooling_off_until = tender.cooling_off_until
    cooling_date_text = cooling_off_until.strftime('%Y-%m-%d %H:%M:%S') if cooling_off_until else 'N/A'
    email_enabled = send_email and bool(
        (settings.EMAIL_HOST_USER and settings.EMAIL_HOST_PASSWORD)
        or str(getattr(settings, 'EMAIL_HOST', '')).lower() in {'mailhog', 'localhost'}
    )

    vendors = User.objects.filter(id__in=list(bids_by_vendor.keys())).only('id', 'email', 'full_name', 'username')
    for vendor in vendors:
        row = bids_by_vendor.get(str(vendor.id))
        if not row:
            continue
        is_winner = row['vendor_id'] == recommended['vendor_id']
        title = (
            f'Notice of Best Evaluated Bidder: {tender.reference_number}'
            if is_winner
            else f'Regret Letter: {tender.reference_number}'
        )
        body = (
            f"Tender: {tender.name} ({tender.reference_number})\n"
            f"Technical Score: {row['technical_score'] if row['technical_score'] is not None else 'N/A'}\n"
            f"Financial Score: {row['financial_score'] if row['financial_score'] is not None else 'Not opened'}\n"
            f"Combined Score: {row['combined_score'] if row['combined_score'] is not None else 'N/A'}\n"
        )
        if is_winner:
            body += (
                f"\nStatus: You are the Best Evaluated Bidder.\n"
                f"Cooling-off period ends on: {cooling_date_text}\n"
                f"The final award and PBA generation will only occur after the cooling-off period expires without a formal protest.\n"
            )
        else:
            body += "\nStatus: Another vendor achieved the highest combined score under the weighted RBF evaluation.\n"
            if row.get('disqualification_reason'):
                body += f"Reason: {row['disqualification_reason']}\n"

        Notification.objects.create(
            recipient_id=str(vendor.id),
            recipient_name=vendor.full_name or vendor.username or vendor.email,
            type=NotificationChannel.EMAIL if email_enabled else NotificationChannel.IN_APP,
            event='intent_to_award',
            title=title,
            body=body,
            status=NotificationStatus.SENT,
            linked_entity_id=str(tender.id),
        )

        if email_enabled and vendor.email:
            try:
                send_mail(
                    subject=title,
                    message=body,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[vendor.email],
                    fail_silently=True,
                )
            except Exception:
                pass


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
        ranking_payload = _build_award_ranking(tender)
        recommended = ranking_payload.get('recommended')
        if not recommended:
            return Response(
                {'detail': 'No qualifying bid passed the technical threshold for intent to award.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if str(recommended['bid_id']) != str(bid.id):
            return Response(
                {
                    'detail': 'Intent to award can only be issued to the recommended winner with the highest combined score.',
                    'recommended_bid_id': recommended['bid_id'],
                    'recommended_vendor_id': recommended['vendor_id'],
                    'recommended_vendor_name': recommended['vendor_name'],
                },
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

        now = timezone.now()
        tender.intent_to_award_bid = bid
        tender.intent_to_award_at = now
        cooling_off_days = tender.cooling_off_days if tender.cooling_off_days is not None else 7
        tender.cooling_off_until = now + timedelta(days=cooling_off_days)
        tender.save(
            update_fields=[
                'intent_to_award_bid',
                'intent_to_award_at',
                'cooling_off_until',
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
            'intent_to_award_issued',
            tender,
            {
                'reference_number': tender.reference_number,
                'bid_id': bid_id,
                'recommended_vendor_id': awarded_vendor_id,
                'recommended_vendor_name': awarded_vendor_name,
                'cooling_off_until': tender.cooling_off_until.isoformat() if tender.cooling_off_until else None,
            },
        )

        send_email = request.data.get('send_email', True)
        _notify_intent_to_award(tender, ranking_payload, send_email)

        data = TenderSerializer(tender).data
        data['award_ranking'] = ranking_payload['rows']
        data['recommended_bid_id'] = recommended['bid_id']
        data['recommended_vendor_id'] = recommended['vendor_id']
        data['recommended_vendor_name'] = recommended['vendor_name']
        return Response(data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['get'])
    def award_ranking(self, request, pk=None):
        tender = self.get_object()
        ranking_payload = _build_award_ranking(tender)
        return Response(ranking_payload, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def confirm_award(self, request, pk=None):
        self._assert_write_permission()
        tender = self.get_object()
        bid = tender.intent_to_award_bid
        if bid is None:
            return Response(
                {'detail': 'Intent to award must be issued before confirming the final award.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if tender.cooling_off_until and timezone.now() < tender.cooling_off_until:
            return Response(
                {
                    'detail': 'Cooling-off period has not yet expired.',
                    'cooling_off_until': tender.cooling_off_until.isoformat(),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            tender.status = TenderStatus.AWARDED
            tender.awarded_vendor_id = bid.vendor_id
            tender.awarded_vendor_name = bid.vendor_name
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
            if bid.status != BidStatus.AWARDED:
                bid.status = BidStatus.AWARDED
                bid.reviewed_at = bid.reviewed_at or timezone.now()
                bid.reviewed_by = bid.reviewed_by or (request.user.full_name or request.user.username)
                bid.save(update_fields=['status', 'reviewed_at', 'reviewed_by', 'updated_at'])

            contract = self._ensure_award_contract(tender, bid, bid.vendor_id)

            log_audit(
                request.user,
                'tender_awarded',
                tender,
                {
                    'reference_number': tender.reference_number,
                    'bid_id': str(bid.id),
                    'awarded_vendor_id': bid.vendor_id,
                    'awarded_vendor_name': bid.vendor_name,
                    'contract_id': str(contract.id) if contract else None,
                },
            )

        send_email = request.data.get('send_email', True)
        self._notify_award(tender, bid.vendor_id, bid.vendor_name, send_email)
        response_data = TenderSerializer(tender, context={'request': request}).data
        if contract:
            response_data['generated_contract'] = TenderContractSerializer(
                contract,
                context={'request': request},
            ).data
        return Response(response_data, status=status.HTTP_200_OK)

    def _notify_award(self, tender: Tender, vendor_id: str, vendor_name: str, send_email=True):
        """Send award notification to winning vendor"""
        from rbf.users.models import User

        try:
            vendor = User.objects.get(id=vendor_id)
        except User.DoesNotExist:
            return

        email_subject = f"Congratulations! You have been awarded {tender.name}"
        email_body = (
            f"Congratulations! You have been awarded {tender.name}.\n\n"
            f"Please review and sign the Performance-Based Agreement to proceed.\n\n"
            f"Tender: {tender.name} ({tender.reference_number})\n"
            f"Department: {tender.department}\n"
            f"Awarded at: {timezone.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"Next step: Log in, open the Contracting tab, review the generated agreement package, and sign the Performance-Based Agreement.\n"
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
        try:
            vendor = User.objects.get(id=vendor_id)
        except User.DoesNotExist:
            return None

        existing = TenderContract.objects.filter(tender=tender, vendor_id=vendor_id).first()
        if existing:
            if bid and not existing.bid_id:
                existing.bid = bid
            _populate_generated_contract_package(existing, tender, bid, vendor)
            existing.save(update_fields=[
                'bid',
                'generated_file',
                'annex_a_file',
                'annex_b_file',
                'annex_c_file',
                'annex_d_file',
                'annex_e_file',
                'updated_at',
            ])
            return existing

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
        _populate_generated_contract_package(contract, tender, bid, vendor)
        contract.save(update_fields=[
            'bid',
            'generated_file',
            'annex_a_file',
            'annex_b_file',
            'annex_c_file',
            'annex_d_file',
            'annex_e_file',
            'updated_at',
        ])
        log_audit(self.request.user, 'contract_generated', contract, {'tender_id': str(tender.id)})
        Notification.objects.create(
            recipient_id=vendor_id,
            recipient_name=vendor.full_name or vendor.username,
            type=NotificationChannel.IN_APP,
            event='contract_generated',
            title=f'Performance-Based Agreement Ready: {tender.reference_number}',
            body=f'Congratulations! You have been awarded {tender.name}. Please review and sign the Performance-Based Agreement to proceed.',
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
        if is_vendor_restricted(request.user):
            raise ValidationError({'detail': 'Your vendor account is suspended or blacklisted. Bid submission is disabled.'})

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
        if is_vendor_restricted(request.user):
            raise ValidationError({'detail': 'Your vendor account is suspended or blacklisted. Bid submission is disabled.'})
        if bid.status not in {BidStatus.DRAFT, BidStatus.SUBMITTED}:
            raise ValidationError({'detail': 'Only draft or submitted bids can be updated.'})

        if bid.tender.status in {TenderStatus.AWARDED, TenderStatus.CLOSED}:
            raise ValidationError({'detail': 'Tender is closed for bidding.'})
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
        if is_vendor_restricted(request.user):
            raise ValidationError({'detail': 'Your vendor account is suspended or blacklisted. Bid submission is disabled.'})
        if bid.status not in {BidStatus.DRAFT, BidStatus.SUBMITTED}:
            raise ValidationError({'detail': 'Only draft or submitted bids can be updated.'})

        if bid.tender.status in {TenderStatus.AWARDED, TenderStatus.CLOSED}:
            raise ValidationError({'detail': 'Tender is closed for bidding.'})
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
        if bid.tender.status in {TenderStatus.AWARDED, TenderStatus.CLOSED}:
            raise ValidationError({'detail': 'Tender is closed for bidding.'})
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
            if bid:
                existing.bid = bid
            source_bid = bid or existing.bid
            update_fields = ['bid', 'updated_at']
            if source_bid:
                _populate_generated_contract_package(existing, tender, source_bid, vendor)
                update_fields.extend([
                    'generated_file',
                    'annex_a_file',
                    'annex_b_file',
                    'annex_c_file',
                    'annex_d_file',
                    'annex_e_file',
                ])
            existing.save(update_fields=update_fields)
            return Response(TenderContractSerializer(existing, context={'request': request}).data, status=status.HTTP_200_OK)

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
        if bid:
            _populate_generated_contract_package(contract, tender, bid, vendor)
            contract.save(update_fields=[
                'generated_file',
                'annex_a_file',
                'annex_b_file',
                'annex_c_file',
                'annex_d_file',
                'annex_e_file',
                'updated_at',
            ])
        log_audit(request.user, 'contract_generated', contract, {'tender_id': str(tender.id)})
        Notification.objects.create(
            recipient_id=vendor_id,
            recipient_name=vendor.full_name or vendor.username,
            type=NotificationChannel.IN_APP,
            event='contract_generated',
            title=f'PBA Package Ready: {tender.reference_number}',
            body='The Performance-Based Agreement and annex package are ready for vendor signature.',
            linked_entity_id=str(tender.id),
        )
        return Response(TenderContractSerializer(contract, context={'request': request}).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def sign(self, request, pk=None):
        contract = self.get_object()
        _hydrate_contract_from_bid(contract)
        if request.user.role != UserRole.VENDOR or contract.vendor_id != str(request.user.id):
            raise PermissionDenied('Only the awarded vendor can sign this contract.')
        if contract.tender.awarded_vendor_id and str(contract.tender.awarded_vendor_id) != str(contract.vendor_id):
            raise ValidationError({'detail': 'Only the awarded vendor can sign this contract.'})
        signed_file = request.data.get('signed_file')
        if not signed_file:
            raise ValidationError({'signed_file': 'Signed contract file is required.'})
        signed_file_name = str(getattr(signed_file, 'name', '') or '').lower()
        if not signed_file_name.endswith('.pdf'):
            raise ValidationError({'signed_file': 'Signed contract must be uploaded as a PDF.'})
        missing_annexes = _missing_contract_annexes(contract)
        if missing_annexes:
            raise ValidationError({'annexes': f"The contract package is incomplete. Missing: {', '.join(missing_annexes)}."})
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
                        body=f'A signed contract package was uploaded by {contract.vendor_name}. Please review and finalize.',
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
        _hydrate_contract_from_bid(contract)
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

        prospect_ok, prospect_msg = push_project_to_prospect(project)
        log_audit(
            request.user,
            'prospect_sync',
            project,
            {'success': prospect_ok, 'message': prospect_msg},
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
                {'name': 'Installation', 'percentage': 50},
                {'name': 'Commissioning', 'percentage': 30},
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

        mobilization_milestone = project.milestones.filter(name__iexact='Mobilization').first()
        if mobilization_milestone and vendor:
            PaymentClaim.objects.create(
                project=project,
                vendor=vendor,
                milestone=mobilization_milestone,
                claim_amount=mobilization_milestone.amount,
                actual_beneficiaries=0,
                actual_female_beneficiaries=0,
                implementation_notes='Auto-generated mobilization payment after contract approval.',
                declaration_accepted=True,
                status=PaymentClaimStatus.PENDING,
            )
            log_audit(request.user, 'mobilization_claim_created', project, {'milestone': mobilization_milestone.id})

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
            body='Your contract has been finalized. The project is now active and the mobilization payment request has been created.',
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
