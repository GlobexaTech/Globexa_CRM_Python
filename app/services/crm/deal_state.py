"""One stage transition invariant for HTTP and approved tool mutations."""

from app.services.crm.common import now


def apply_stage(deal, stage):
    deal.stage_id = stage.id
    deal.probability = stage.probability
    deal.weighted_value = int(deal.value * stage.probability / 100)
    deal.actual_close_date = (deal.actual_close_date or now()) if stage.is_closed else None
