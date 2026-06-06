from apps.api.models import Account


def render_account(account: Account) -> str:
    return account.email
