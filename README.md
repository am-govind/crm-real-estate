# LandForge CRM

### Turn land opportunities into decisions.

LandForge is a property-centered land acquisition CRM for teams that need to move from **“someone mentioned a parcel”** to **“the deal is verified, funded, and closed”**—with every owner, document, task, map, approval, and payment milestone connected to the land itself.

```text
Lead → Property → Owners → Due Diligence → Negotiation
                                  ↓
                   Agreement → Payment → Registration → Closed
```

The product is designed for India-first land operations, multi-tenant SaaS, field teams, legal reviewers, and acquisition managers.

## The idea

Most CRMs are contact-first. Land deals are different.

One owner may offer several properties. One property may go through several acquisition attempts. Every deal depends on documents, surveys, approvals, map references, and multiple stakeholders.

LandForge keeps the **property/parcel as the center of gravity**:

```text
Owner
  └── Property / Land Parcel
        ├── Site maps and plot inventory
        ├── Historical deals
        ├── Documents and approvals
        ├── Due-diligence checklists
        ├── Site visits and tasks
        └── Payment milestones
```

## What is already here

### Deal control center

See the whole acquisition at a glance:

- Current stage and progress
- Owners and verification status
- Document completeness
- Legal, technical, revenue, and survey health
- Asking, negotiated, advance, and balance values
- Next action, assignee, and due date

### Property and owner intelligence

- Multiple owners per property
- Ownership percentages
- Historical ownership snapshots per deal
- One owner linked to many properties
- Multiple historical deals per property
- Configurable active-deal override for exceptional cases

### Workflow with accountability

Every stage can carry its own checklist. Stage transitions are auditable, backward movement requires a reason, and skipped work is recorded as intentionally bypassed rather than silently completed.

### Document vault

Store and govern title documents, revenue records, survey files, agreements, identity documents, payment receipts, and more—with classifications, versions, review status, permissions, expiry data, and audit history.

### Site and plot registry

Track land plots, apartments, studio flats, and commercial units using property-type-specific templates.

- Human-readable immutable IDs such as `SITE-000001`
- Map/document traceability
- Plot labels and structured locations
- Area and dimensions
- Irregular plot edges and cut dimensions
- Carpet, built-up, rooms, floors, frontage, access, and usage fields
- Pending → administrator approval workflow
- Deterministic search and filtering

### Map-first field operations

- OpenStreetMap-compatible mapping
- MapLibre-based rendering
- GeoJSON/KML support
- PDF and image map uploads
- Manual tracing for scanned maps
- Versioned geometries
- Technical/legal review before activation
- Area, perimeter, and nearby-road/city/highway calculations

### Web and mobile

- React + TypeScript + Vite web CRM
- React Native + Expo mobile application
- Shared FastAPI backend and generated API client
- Mobile flows for visits, GPS, photos, tasks, and field updates

## Architecture

```text
┌─────────────────────┐      ┌─────────────────────┐
│ React Web CRM       │      │ React Native + Expo │
└──────────┬──────────┘      └──────────┬──────────┘
           │ REST / OpenAPI             │
           └──────────────┬────────────┘
                          ▼
                ┌──────────────────┐
                │ FastAPI API      │
                │ Modular monolith │
                └──────┬───────┬───┘
                       │       │
          ┌────────────┘       └─────────────┐
          ▼                                  ▼
┌──────────────────┐                ┌─────────────────┐
│ PostgreSQL       │                │ Worker          │
│ + PostGIS        │                │ Redis-backed    │
└──────────────────┘                └───────┬─────────┘
                                            ▼
                                   ┌─────────────────┐
                                   │ S3-compatible   │
                                   │ private storage │
                                   └─────────────────┘
```

The system is intentionally a **modular monolith first**. It can scale horizontally and later extract independent workloads—document processing, notifications, reporting, or search—when real operational boundaries justify it.

## Technology choices

| Layer | Technology |
|---|---|
| Web | React, TypeScript, Vite |
| Mobile | React Native, Expo |
| API | FastAPI, REST, OpenAPI |
| Database | PostgreSQL, PostGIS |
| Background work | Redis-compatible queue and worker |
| File storage | S3-compatible object storage |
| Maps | MapLibre GL, OpenStreetMap-compatible providers |
| Authentication | OIDC; Keycloak locally, managed provider in early production |
| Authorization | Backend-enforced tenant, role, property, and deal permissions |

## Repository map

```text
apps/
  api/       FastAPI modular monolith
  mobile/    React Native + Expo application
  web/       React + Vite CRM
  worker/    Background processing

packages/
  api-client/  Shared API client
  config/      Shared TypeScript configuration
  domain/      Shared domain types and primitives
  ui/          Shared UI package foundation

migrations/   Database configuration and security policies
```

## Run locally

### Prerequisites

- Node.js
- pnpm
- Python 3.11+
- PostgreSQL with PostGIS, or Docker
- Redis, or Docker
- Keycloak for local OIDC development

Install JavaScript dependencies:

```bash
pnpm install
```

Run the web application:

```bash
pnpm dev:web
```

Run the mobile application:

```bash
pnpm dev:mobile
```

Run checks:

```bash
pnpm typecheck
pnpm lint
pnpm build
```

The API and worker use their own Python project metadata under `apps/api` and `apps/worker`.

## Security model

Authentication is delegated to OIDC. Business authorization remains inside the API.

- Keycloak is used locally during development.
- Early production can use a managed provider with a free tier, such as Zitadel or Auth0.
- Enterprise customers can later bring Microsoft, Google, or another OIDC provider.
- Tenant boundaries are enforced in the service layer first and are designed for PostgreSQL row-level security.
- Sensitive documents require explicit permissions.
- Important changes produce audit events.
- Original map files are immutable; derived geometries are versioned.

## Product principles

1. The land parcel is the center of the system.
2. A deal is an acquisition attempt, not the property itself.
3. Preserve history instead of overwriting facts.
4. Human approval remains authoritative for legal and technical verification.
5. Configuration belongs in versioned templates.
6. Mobile field work is a first-class workflow.
7. Cloud, map, and identity providers remain replaceable.
8. Structured data beats memory; audit trails beat assumptions.

## Roadmap

- Platform foundation, tenancy, OIDC, permissions, and audit
- Owners, properties, and ownership history
- Deals, workflows, stages, checklists, and tasks
- Document vault and review controls
- Site-map processing and approved geometry
- Payment milestones and site visits
- Deal control center, scoring, and map dashboard
- Offline mobile synchronization and production hardening

Planned later: broker portals, calendar sync, OCR, e-signatures, accounting integrations, satellite analysis, advanced land-use intelligence, and independently deployed services.

## Status

This repository contains the initial product scaffold and implementation foundation. The full product is being built incrementally behind the architecture and domain decisions documented in [`LAND_DEAL_CRM_PLAN.md`](./LAND_DEAL_CRM_PLAN.md).

## License

License terms are not yet finalized.
