"""
Day 1 Topic 1 — Microservice Principles
This file is conceptual — read and understand, no running needed.
"""

# ============================================================
# THE FOUR PRINCIPLES OF GOOD MICROSERVICES
# ============================================================

"""
1. SINGLE RESPONSIBILITY
   Each service does ONE thing well.

   Bad:  "User Service" handles auth + profiles + notifications + billing
   Good: Auth Service, Profile Service, Notification Service, Billing Service

2. OWN YOUR DATA
   Each service has its own database.
   No service queries another service's DB directly.

   Bad:  LLM Service does: SELECT * FROM auth_service.users WHERE id=$1
   Good: LLM Service calls Auth Service API: GET /users/{id}

3. COMMUNICATE THROUGH APIs
   Services talk via HTTP (sync) or message queues (async).
   Never shared memory, never shared DB.

   HTTP/gRPC: Request needs an immediate response
   Message Queue: Fire and forget, async processing

4. FAIL INDEPENDENTLY
   If LLM Gateway is down, Auth still works.
   Use circuit breakers (Phase 5) between services.
   Design for partial failure.
"""


# ============================================================
# DOMAIN BOUNDARIES — how to find the right splits
# ============================================================

"""
For the IT Operations AI system (your job):

┌─────────────────────────────────────────────────────┐
│                  Domain Map                          │
│                                                      │
│  Identity Domain    │  Content Domain                │
│  ─────────────────  │  ──────────────                │
│  Auth Service       │  Document Ingestion Service    │
│  User Service       │  Retrieval Service             │
│  SSO/SAML           │  Vector DB                     │
│                     │                                │
│  Intelligence Domain│  Integration Domain            │
│  ─────────────────  │  ──────────────                │
│  LLM Gateway        │  ServiceNow Connector          │
│  Agent Service      │  Jira Connector                │
│  Langfuse Tracing   │  Azure DevOps Connector        │
│                                                      │
│  Platform Domain                                     │
│  ─────────────────                                   │
│  API Gateway                                         │
│  Notification Service                                │
│  Audit Log Service                                   │
└─────────────────────────────────────────────────────┘

Each box = a candidate microservice
Each domain = a candidate team
"""


# ============================================================
# COMMUNICATION PATTERNS
# ============================================================

"""
SYNCHRONOUS (HTTP/gRPC):
Request → wait → Response
Use when: caller needs the result immediately

Example: API Gateway → Auth Service (must verify token before proceeding)
         User requests → LLM Gateway (needs response to show user)

ASYNCHRONOUS (Message Queue):
Producer → puts message → Queue → Consumer picks up when ready
Use when: caller doesn't need immediate result, or work takes long time

Example: Document uploaded → Ingestion Service queues chunking job
         LLM response generated → Audit Log Service records it
         Incident created → Notification Service sends email

HYBRID (most real systems):
Critical path:   synchronous (must be fast)
Background work: asynchronous (can be slow)

Example:
User uploads doc → API Gateway → Ingestion Service
                                ↓ sync response: "uploaded, processing..."
                                ↓ async message → Chunking Worker
                                                → Embedding Worker
                                                → Vector Store Worker
User gets instant response. Processing happens in background.
"""

print("Day 1 Topic 1 — Read and understand, no execution needed")
print("Key insight: microservices solve organizational and scaling problems,")
print("not technical ones. Start as monolith.")