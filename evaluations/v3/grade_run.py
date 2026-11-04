"""Run frozen grade_blind.py with the judge cap set to this round's DeepSeek remainder (49)."""
import asyncio

import grade_blind

original = grade_blind.Budget.from_context


def capped(config):
    budget = original(config)
    budget.total_cny = 49
    return budget


grade_blind.Budget.from_context = staticmethod(capped)
asyncio.run(grade_blind.main())
