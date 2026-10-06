"""One definition of what each payment-claim status means for reporting.

Claims move Submitted -> RMT Approved -> TAC Endorsed -> PSC Approved -> Completed (paid),
and older records still carry the legacy Pending / Verified / Approved / Paid values.
Every report and dashboard should count money through these groups so totals agree.
"""
from .models import PaymentClaimStatus as S

PAID = frozenset({S.COMPLETED, S.LEGACY_PAID})
APPROVED_AWAITING_PAYMENT = frozenset({S.PSC_APPROVED, S.LEGACY_APPROVED})
IN_REVIEW = frozenset({S.SUBMITTED, S.RMT_APPROVED, S.TAC_ENDORSED, S.LEGACY_PENDING, S.LEGACY_VERIFIED})
HELD = frozenset({S.HELD_AUDIT})
REJECTED = frozenset({S.REJECTED})
# Approved by the PSC, whether or not the money has gone out yet.
APPROVED = PAID | APPROVED_AWAITING_PAYMENT


def stage(status: str) -> str:
    if status in PAID:
        return 'Paid'
    if status in APPROVED_AWAITING_PAYMENT:
        return 'Approved, awaiting payment'
    if status in HELD:
        return 'Held for audit'
    if status in REJECTED:
        return 'Rejected'
    return 'In review'
