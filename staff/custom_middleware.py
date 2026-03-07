from django.conf import settings
from django.http import HttpResponseForbidden
from django.urls import resolve, reverse
from rest_framework_simplejwt.authentication import JWTAuthentication
import logging
import jwt
from hospital import settings
from rest_framework.authtoken.models import Token

logger = logging.getLogger(__name__)

# token = Token.objects.get(key='eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoxMSwiaWQiOjExLCJleHAiOjE3MzY5NzE5MDMsInRva2VuX3R5cGUiOiJhY2Nlc3MifQ.GloBhzadNlmryc68DE2cv1LD_FjPitO3EjMlNKiZZkg')
# print('the.  user is', token.user, token.user_id)


def dynamic_login_url(request):
    if request.path.startswith('/staff/'):
        request.login_url = reverse('staff:login')  # staff login URL
    else:
        request.login_url = settings.LOGIN_URL  # Default login URL

class DynamicLoginURLMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        dynamic_login_url(request)  # Call the request processor
        response = self.get_response(request)
        return response


class StaffOnlyMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        resolver_match = resolve(request.path)
        url_name = resolver_match.url_name
        app_name = resolver_match.app_name

        # 1. Allow non-staff apps and login/register pages
        if app_name != 'staff' or url_name in ['login', 'register', 'staff-register', 'staff-login']:
            return self.get_response(request)

        # 2. Check Standard Browser Session (For your Dashboard Views)
        if request.user.is_authenticated:
            if hasattr(request.user, 'staff_profile'):
                return self.get_response(request)

        # 3. Check API JWT Token (For Mobile Apps or Postman)
        jwt_auth = JWTAuthentication()
        try:
            auth_result = jwt_auth.authenticate(request)
            if auth_result:
                user, token = auth_result
                if hasattr(user, 'staff_profile'):
                    # Attach the user to the request so your views know who they are!
                    request.user = user
                    return self.get_response(request)
        except Exception:
            # If token is expired or invalid, silently fail and let it hit the Forbidden response below
            pass

        # 4. If neither Session nor JWT worked, block them.
        return HttpResponseForbidden("You must be a staff member to access this resource.")


class DebugToolbarExcludeAPIMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # Exclude JSON/DRF API responses from Debug Toolbar
        if request.path.startswith('staff/api/') or response.get('Content-Type', '').startswith('application/json'):
            return response

        return response
