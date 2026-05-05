"""
Day 1 — SSO Concepts Illustrated in Code

No real SSO server needed today.
We simulate the flows to understand every step.
"""

import os,sys
sys.path.insert(0,os.path.dirname(os.path.dirname(__file__)))

import base64
import uuid
import time
import hashlib
import json
from datetime import datetime, timedelta
from typing import Optional
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from pydantic import BaseModel

app=FastAPI(title="SSO Concepts Demo")

# ============================================================
# SIMULATED IDENTITY PROVIDER
# ============================================================

# Fake corporate directory — in real life this is Okta/Azure AD
CORPORATE_DIRECTORY = {
    "alice@company.com": {
        "id":          "user_001",
        "email":       "alice@company.com",
        "first_name":  "Alice",
        "last_name":   "Smith",
        "department":  "Engineering",
        "title":       "Senior Engineer",
        "groups":      ["Engineering", "Admins", "LLM-Platform"],
        "is_active":   True
    },
    "bob@company.com": {
        "id":          "user_002",
        "email":       "bob@company.com",
        "first_name":  "Bob",
        "last_name":   "Jones",
        "department":  "Engineering",
        "title":       "Engineer",
        "groups":      ["Engineering", "LLM-Platform"],
        "is_active":   True
    },
    "carol@company.com": {
        "id":          "user_003",
        "email":       "carol@company.com",
        "first_name":  "Carol",
        "last_name":   "White",
        "department":  "Finance",
        "title":       "Finance Manager",
        "groups":      ["Finance"],
        "is_active":   True
    }
}

# Active sessions in our "IdP" Stores the employee details
idp_sessions:dict={}

# Pending SAML requests — RelayState → original URL to understand this 
# 1. User wants to go to: https://expense.com/reports
#                                          ↓
# 2. App redirects to Okta for login
#                                          ↓
# 3. User logs into Okta
#                                          ↓
# 4. Okta sends SAML response back to: https://expense.com/saml/callback
#                                          ↓
# 5. App validates SAML, creates session
#                                          ↓
# 6. Where does the app send the user now?
#    → Homepage? 
#    → Dashboard?
#    → Login page?
   
#    ❌ The app FORGOT user wanted to go to /reports!
# The Solution: pending_saml_requests ✅
pending_saml_requests:dict={}

# App sessions (what your SP creates after SSO) Stores the details for jwt tokens which is done inside the app
app_sessions:dict={}

# ============================================================
# SIMULATE: SAML REQUEST BUILDING
# ============================================================
def build_saml_request(relay_state: str) -> str:
    """
    In production python3-saml builds this XML.
    Here we show what's inside a SAMLRequest.

    The SAMLRequest is a base64-encoded compressed XML document
    that tells the IdP:
    - Who is asking (your app's entity ID)
    - Where to send the response (your ACS URL)
    - What you want (authentication assertion)
    - A unique request ID to prevent replay attacks
    """
    request_id = f"id_{uuid.uuid4().hex}"
    issue_time = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    saml_request_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<samlp:AuthnRequest
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="{request_id}"
    Version="2.0"
    IssueInstant="{issue_time}"
    AssertionConsumerServiceURL="https://yourapp.com/auth/saml/acs"
    ProtocolBinding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
    ProviderName="Your Gen AI App">

    <saml:Issuer>
        https://yourapp.com/saml/metadata
    </saml:Issuer>

    <samlp:NameIDPolicy
        Format="urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress"
        AllowCreate="true"/>

    <samlp:RequestedAuthnContext Comparison="exact">
        <saml:AuthnContextClassRef>
            urn:oasis:names:tc:SAML:2.0:ac:classes:PasswordProtectedTransport
        </saml:AuthnContextClassRef>
    </samlp:RequestedAuthnContext>
</samlp:AuthnRequest>"""

    # In production: deflate compress + base64 encode
    encoded = base64.b64encode(saml_request_xml.encode()).decode()
    return encoded, request_id


def build_saml_response(user: dict, request_id: str) -> str:
    """
    What the IdP sends back to your ACS endpoint.
    Contains the user's identity as signed XML assertions.

    Key assertions:
    - NameID: the user's email address
    - Attributes: name, department, groups etc.
    - Conditions: when this assertion is valid (time window)
    - Signature: cryptographic proof this came from the IdP
    """
    response_id  = f"id_{uuid.uuid4().hex}"
    assertion_id = f"id_{uuid.uuid4().hex}"
    now          = datetime.utcnow()
    valid_until  = now + timedelta(minutes=5)   # SAML assertions expire quickly

    saml_response_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<samlp:Response
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="{response_id}"
    InResponseTo="{request_id}"
    Version="2.0"
    IssueInstant="{now.strftime('%Y-%m-%dT%H:%M:%SZ')}"
    Destination="https://yourapp.com/auth/saml/acs">

    <saml:Issuer>https://company.okta.com</saml:Issuer>

    <samlp:Status>
        <samlp:StatusCode Value="urn:oasis:names:tc:SAML:2.0:status:Success"/>
    </samlp:Status>

    <saml:Assertion
        xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
        ID="{assertion_id}"
        Version="2.0"
        IssueInstant="{now.strftime('%Y-%m-%dT%H:%M:%SZ')}">

        <saml:Issuer>https://company.okta.com</saml:Issuer>

        <!-- WHO is this assertion about -->
        <saml:Subject>
            <saml:NameID Format="urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress">
                {user['email']}
            </saml:NameID>
            <saml:SubjectConfirmation Method="urn:oasis:names:tc:SAML:2.0:cm:bearer">
                <saml:SubjectConfirmationData
                    InResponseTo="{request_id}"
                    NotOnOrAfter="{valid_until.strftime('%Y-%m-%dT%H:%M:%SZ')}"
                    Recipient="https://yourapp.com/auth/saml/acs"/>
            </saml:SubjectConfirmation>
        </saml:Subject>

        <!-- WHEN is this assertion valid -->
        <saml:Conditions
            NotBefore="{now.strftime('%Y-%m-%dT%H:%M:%SZ')}"
            NotOnOrAfter="{valid_until.strftime('%Y-%m-%dT%H:%M:%SZ')}">
            <saml:AudienceRestriction>
                <saml:Audience>https://yourapp.com/saml/metadata</saml:Audience>
            </saml:AudienceRestriction>
        </saml:Conditions>

        <!-- USER ATTRIBUTES — this is the gold -->
        <saml:AttributeStatement>
            <saml:Attribute Name="firstName">
                <saml:AttributeValue>{user['first_name']}</saml:AttributeValue>
            </saml:Attribute>
            <saml:Attribute Name="lastName">
                <saml:AttributeValue>{user['last_name']}</saml:AttributeValue>
            </saml:Attribute>
            <saml:Attribute Name="department">
                <saml:AttributeValue>{user['department']}</saml:AttributeValue>
            </saml:Attribute>
            <saml:Attribute Name="title">
                <saml:AttributeValue>{user['title']}</saml:AttributeValue>
            </saml:Attribute>
            <saml:Attribute Name="groups">
                {''.join(f'<saml:AttributeValue>{g}</saml:AttributeValue>' for g in user['groups'])}
            </saml:Attribute>
        </saml:AttributeStatement>

        <!-- SIGNATURE — in production: RSA-SHA256 signed by IdP private key -->
        <!-- Your SP validates this using the IdP's public certificate -->
        <ds:Signature xmlns:ds="http://www.w3.org/2000/09/xmldsig#">
            SIMULATED_SIGNATURE_{hashlib.sha256(user['email'].encode()).hexdigest()[:16]}
        </ds:Signature>

    </saml:Assertion>
</samlp:Response>"""

    return base64.b64encode(saml_response_xml.encode()).decode()


# ============================================================
# SP ROUTES — your FastAPI application
# ============================================================

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    """
    Protected route — redirects to SSO if no session.
    This is where the SSO flow starts.
    """
    session_id = request.cookies.get("session_id")

    if not session_id or session_id not in app_sessions:
        # No session → initiate SSO
        relay_state = f"relay_{uuid.uuid4().hex[:8]}"
        # Remember where user was going
        pending_saml_requests[relay_state] = "/dashboard"

        encoded_request, request_id = build_saml_request(relay_state)

        # Redirect to IdP (simulated)
        return HTMLResponse(f"""
        <html><body>
        <h3>No session — redirecting to corporate SSO...</h3>
        <p>In production this redirects to:</p>
        <code>https://company.okta.com/sso/saml?SAMLRequest={encoded_request[:50]}...
        &RelayState={relay_state}</code>
        <br><br>
        <p>Simulating SSO login — pick a user:</p>
        <a href="/simulate/idp/login?relay={relay_state}&email=alice@company.com">
            Login as Alice (Engineering/Admin)
        </a><br>
        <a href="/simulate/idp/login?relay={relay_state}&email=bob@company.com">
            Login as Bob (Engineering)
        </a><br>
        <a href="/simulate/idp/login?relay={relay_state}&email=carol@company.com">
            Login as Carol (Finance)
        </a>
        </body></html>
        """)

    user = app_sessions[session_id]
    return HTMLResponse(f"""
    <html><body>
    <h2>✅ Dashboard — SSO Session Active</h2>
    <p>Welcome, <b>{user['first_name']} {user['last_name']}</b></p>
    <p>Email:      {user['email']}</p>
    <p>Department: {user['department']}</p>
    <p>Title:      {user['title']}</p>
    <p>Groups:     {', '.join(user['groups'])}</p>
    <br>
    <a href="/auth/saml/logout">Logout</a>
    </body></html>
    """)


# ============================================================
# SIMULATE: IdP LOGIN PAGE
# ============================================================

@app.get("/simulate/idp/login", response_class=HTMLResponse)
def simulate_idp_login(relay: str, email: str):
    """
    Simulates what happens at the IdP.
    In production: user logs into Okta/Azure AD here.
    IdP then POSTs SAMLResponse to your ACS URL.
    """
    user = CORPORATE_DIRECTORY.get(email)
    if not user:
        return HTMLResponse("<h3>User not found in corporate directory</h3>")

    if not user["is_active"]:
        return HTMLResponse("<h3>Account disabled — contact IT</h3>")

    # Simulate IdP creating the assertion and posting to ACS
    saml_response = build_saml_response(user, f"simulated_request_{relay}")

    # Return auto-submitting form — exactly what real IdPs do
    # Browser automatically POSTs this to your ACS endpoint
    return HTMLResponse(f"""
    <html>
    <body onload="document.forms[0].submit()">
        <h3>Authenticated at IdP — redirecting back to app...</h3>
        <form method="POST" action="/auth/saml/acs">
            <input type="hidden" name="SAMLResponse" value="{saml_response}"/>
            <input type="hidden" name="RelayState"   value="{relay}"/>
            <input type="submit" value="Click if not redirected automatically"/>
        </form>
    </body>
    </html>
    """)


# ============================================================
# ACS ENDPOINT — Assertion Consumer Service
# This is the most important endpoint in SAML
# ============================================================

@app.post("/auth/saml/acs")
async def assertion_consumer_service(request: Request):
    """
    ACS = Assertion Consumer Service.
    This is where the IdP POSTs the SAMLResponse after auth.

    In production with python3-saml:
    1. Validate XML signature using IdP's public certificate
    2. Check timestamps — NotBefore, NotOnOrAfter
    3. Check Audience — must match your entity ID
    4. Check InResponseTo — must match your original request
    5. Extract NameID (email) and attributes
    6. Create your own session

    We simulate steps 1-4 here.
    """
    form_data     = await request.form()
    saml_response = form_data.get("SAMLResponse", "")
    relay_state   = form_data.get("RelayState", "")

    if not saml_response:
        raise HTTPException(status_code=400, detail="No SAMLResponse in POST body")

    # Decode the response
    try:
        decoded = base64.b64decode(saml_response).decode()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid SAMLResponse encoding")

    # In production — python3-saml validates signature here
    # For simulation — extract email from our fake XML
    email = None
    for line in decoded.split("\n"):
        line = line.strip()
        if "@company.com" in line and "saml:NameID" not in line:
            import re
            match = re.search(r'[\w\.-]+@company\.com', line)
            if match:
                email = match.group()
                break

    if not email or email not in CORPORATE_DIRECTORY:
        raise HTTPException(status_code=401, detail="Could not extract valid email from SAML assertion")

    user = CORPORATE_DIRECTORY[email]

    # Create app session
    session_id = uuid.uuid4().hex
    app_sessions[session_id] = user

    # Determine redirect URL from RelayState
    redirect_url = pending_saml_requests.pop(relay_state, "/dashboard")

    print(f"[SSO] User authenticated via SAML: {email}")
    print(f"[SSO] Groups: {user['groups']}")
    print(f"[SSO] Redirecting to: {redirect_url}")

    # Set session cookie and redirect
    response = RedirectResponse(url=redirect_url, status_code=302)
    response.set_cookie(
        key="session_id",
        value=session_id,
        httponly=True,     # JS can't read it
        samesite="lax",    # CSRF protection
        max_age=3600       # 1 hour
    )
    return response


@app.get("/auth/saml/logout")
def saml_logout(request: Request):
    """
    Single Logout (SLO) — logs out from your app AND the IdP.
    In production also calls IdP's SLO endpoint so
    logging out of one app logs out of all apps.
    """
    session_id = request.cookies.get("session_id")
    if session_id and session_id in app_sessions:
        user = app_sessions.pop(session_id)
        print(f"[SSO] User logged out: {user['email']}")

    response = RedirectResponse(url="/dashboard", status_code=302)
    response.delete_cookie("session_id")
    return response


# ============================================================
# METADATA ENDPOINT — required for SAML setup
# ============================================================

@app.get("/saml/metadata")
def saml_metadata():
    """
    Your SP metadata — share this XML with the IdP admin.
    The IdP admin configures their system with this file.
    This is how you "connect" your app to Okta/Azure AD.

    Contains:
    - Your entity ID (unique identifier for your app)
    - Your ACS URL (where IdP should POST assertions)
    - Your public certificate (for encrypting assertions)
    - Supported name ID formats
    """
    metadata = """<?xml version="1.0" encoding="UTF-8"?>
<md:EntityDescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    entityID="https://yourapp.com/saml/metadata">

    <md:SPSSODescriptor
        AuthnRequestsSigned="true"
        WantAssertionsSigned="true"
        protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">

        <!-- Your X.509 certificate for encryption -->
        <md:KeyDescriptor use="signing">
            <ds:KeyInfo xmlns:ds="http://www.w3.org/2000/09/xmldsig#">
                <ds:X509Data>
                    <ds:X509Certificate>YOUR_BASE64_CERTIFICATE_HERE</ds:X509Certificate>
                </ds:X509Data>
            </ds:KeyInfo>
        </md:KeyDescriptor>

        <!-- Where IdP sends the SAMLResponse -->
        <md:AssertionConsumerService
            Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
            Location="https://yourapp.com/auth/saml/acs"
            index="1"/>

        <!-- Where IdP sends logout requests -->
        <md:SingleLogoutService
            Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
            Location="https://yourapp.com/auth/saml/slo"/>

    </md:SPSSODescriptor>

    <!-- Your app's human-readable info (shown in Okta admin UI) -->
    <md:Organization>
        <md:OrganizationName>Your Company</md:OrganizationName>
        <md:OrganizationDisplayName>Gen AI Platform</md:OrganizationDisplayName>
        <md:OrganizationURL>https://yourapp.com</md:OrganizationURL>
    </md:Organization>

</md:EntityDescriptor>"""

    from fastapi.responses import Response
    return Response(content=metadata, media_type="application/xml")

