"""Fixed rendering of the complete receipt, including its evidence qualifications."""

from __future__ import annotations

import json
from typing import Any


def render(result: dict[str, Any]) -> str:
    if 'revalidation_version' in result:
        return (
            f'Revalidation: {result["status"]}. '
            f'Outcome categories unchanged: {result["outcomes_unchanged"]}.\n'
            'Use the current receipt and its scope; unchanged does not establish truth.\n\n'
            + json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
            + '\n'
        )
    if 'question_contract' in result:
        return (
            result['answer']
            + '\n\n'
            + json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
            + '\n'
        )
    rows = [
        'Framework coverage: recorded mapping coverage, not a capability or achievement score.',
        result['scope'],
        f'Complete: {result["complete"]}',
    ]
    for criterion in result['criteria']:
        rows.append(f'{criterion["criterion"]}: {criterion["outcome"].replace("_", " ")}')
    # Keep the receipt verbatim below the summary: shortening quotes or dropping
    # premises here would let the human-readable view overstate the calculation.
    rows.extend(['', json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)])
    return '\n'.join(rows) + '\n'
