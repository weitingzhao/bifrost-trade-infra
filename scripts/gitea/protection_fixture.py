"""Independent Gitea 1.21.11 response fields for offline protection tests."""
from copy import deepcopy

PROTECTION_DEFAULTS = {
    "enable_push": False,
    "enable_push_whitelist": False,
    "push_whitelist_usernames": [],
    "push_whitelist_teams": [],
    "push_whitelist_deploy_keys": False,
    "enable_merge_whitelist": False,
    "merge_whitelist_usernames": [],
    "merge_whitelist_teams": [],
    "enable_status_check": False,
    "status_check_contexts": [],
    "required_approvals": 0,
    "enable_approvals_whitelist": False,
    "approvals_whitelist_username": [],
    "approvals_whitelist_teams": [],
    "block_on_rejected_reviews": False,
    "block_on_official_review_requests": False,
    "block_on_outdated_branch": False,
    "dismiss_stale_approvals": False,
    "require_signed_commits": False,
    "protected_file_patterns": "",
    "unprotected_file_patterns": "",
}


def protection_rule(name, **fields):
    return {**deepcopy(PROTECTION_DEFAULTS), "rule_name": name, **fields}
