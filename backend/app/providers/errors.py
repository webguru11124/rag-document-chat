import anthropic
import openai
from google.genai import errors as google_errors


class ProviderError(Exception):
    """An error worth showing to the user, with the HTTP status to answer with."""

    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def translate(exc: Exception, provider_label: str) -> ProviderError:
    """Turn an SDK exception into a short, user-facing ProviderError."""
    if isinstance(exc, ProviderError):
        return exc

    if isinstance(exc, (openai.AuthenticationError, anthropic.AuthenticationError)):
        return ProviderError(f"{provider_label} rejected the API key.", 401)
    if isinstance(exc, (openai.PermissionDeniedError, anthropic.PermissionDeniedError)):
        return ProviderError(f"{provider_label} denied access to this model for your key.", 403)
    if isinstance(exc, (openai.NotFoundError, anthropic.NotFoundError)):
        return ProviderError(f"{provider_label} doesn't know this model. Pick another one.", 404)
    if isinstance(exc, (openai.RateLimitError, anthropic.RateLimitError)):
        return ProviderError(f"{provider_label} rate limit or quota reached. Try again shortly.", 429)
    if isinstance(exc, (openai.BadRequestError, anthropic.BadRequestError)):
        return ProviderError(f"{provider_label} rejected the request: {_api_message(exc)}", 400)
    if isinstance(exc, (openai.APIConnectionError, anthropic.APIConnectionError)):
        return ProviderError(f"Couldn't reach {provider_label}. Check the server's network.", 502)
    if isinstance(exc, (openai.APIStatusError, anthropic.APIStatusError)):
        return ProviderError(f"{provider_label} returned an error: {_api_message(exc)}", 502)

    if isinstance(exc, google_errors.APIError):
        code = getattr(exc, "code", None) or 502
        if code in (401, 403) or "API key" in str(exc):
            return ProviderError(f"{provider_label} rejected the API key.", 401)
        if code == 404:
            return ProviderError(f"{provider_label} doesn't know this model. Pick another one.", 404)
        if code == 429:
            return ProviderError(f"{provider_label} rate limit or quota reached. Try again shortly.", 429)
        return ProviderError(f"{provider_label} returned an error: {getattr(exc, 'message', exc)}", 502)

    return ProviderError(f"{provider_label} call failed: {exc}", 502)


def _api_message(exc: Exception) -> str:
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict) and error.get("message"):
            return str(error["message"])
    return getattr(exc, "message", None) or str(exc)
