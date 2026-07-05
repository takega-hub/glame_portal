# GLAME AI PLATFORM — BOARD SYSTEM & UI LOGIC SPECIFICATION

# 1. PURPOSE OF DOCUMENT

This document describes:

- board architecture
- operational UI logic
- task structure
- statuses
- board relationships
- agent interaction logic
- dashboard structure
- approval UI
- analytics visualization
- workflow behaviour

The goal is to prevent the developer from building:

- generic kanban boards
- Notion-style chaos
- simple task lists
- disconnected AI chats

The system must behave as:

```md
AI-native luxury retail operating system
```

---

# 2. CORE BOARD PRINCIPLES

The board system must:

- support operational clarity
- reduce chaos
- support approvals
- support AI orchestration
- support cross-agent workflows
- support analytics visibility
- support campaign tracking
- support behavioural retail logic

---

# 3. BOARD TYPES

The platform must contain the following core boards.

---

# 3.1 MARKETING COMMAND BOARD

## Purpose

Central operational command center.

This is the main board used by:

- Elena
- AI Marketing Director
- leadership layer

---

## Main Goals

- see entire system status
- track priorities
- track campaigns
- track risks
- monitor agents
- approve decisions
- manage operational focus

---

## UI PRIORITY

This board must feel:

- executive
- minimal
- strategic
- highly readable
- low-noise
- premium

NOT:

- overloaded kanban
- startup dashboard chaos
- developer admin panel

---

# MAIN SECTIONS

## A. Priority Strip

Horizontal top block.

Shows:

- P0 critical tasks
- blocked workflows
- overdue approvals
- critical risks
- traffic anomalies
- CRM failures

Visual priority:

```md
always visible
```

---

## B. Weekly Focus Panel

Shows:

- weekly campaign focus
- key launches
- arrivals
- production focus
- partnership focus
- app focus

---

## C. AI Agent Status Grid

Shows all agents.

Each card includes:

- agent name
- current status
- active tasks
- blocked tasks
- pending approvals
- last update
- health status

---

## D. Operational Timeline

Shows:

- today
- tomorrow
- next 7 days

Must include:

- publications
- CRM sends
- productions
- collabs
- launches
- reviews

---

## E. Approval Queue

Dedicated approval section.

Shows:

- pending approvals
- priority
- deadline
- requesting agent
- risk level
- approve / reject / revise actions

---

## F. Analytics Snapshot

Quick business snapshot.

Must include:

- traffic
- sales
- saves
- CRM activity
- app activity
- growth trends

---

# UI COMPONENTS

Required:

- status pills
- risk indicators
- approval badges
- deadline countdowns
- agent avatars/icons
- quick filters
- campaign tags
- city tags
- DNA tags

---

# 3.2 CONTENT BOARD

## Purpose

Central content operating board.

Managed primarily by:

- AI Brand Media
- AI Personal Media
- Content Producer

---

## Main Goals

- content planning
- production management
- publication management
- content analytics
- content archive
- cross-channel coordination

---

# BOARD STRUCTURE

## A. Content Calendar View

Default view.

Must support:

- day
- week
- month
- campaign mode

---

## B. Production Pipeline

Columns:

```md
Idea
Briefed
Planned
In Production
Editing
Needs Approval
Approved
Scheduled
Published
Measured
Done
```

---

## C. Media Layer Filters

Must filter by:

- Personal Media
- GLAME Brand Media
- Campaign
- CRM Support Content
- Partnership Content
- App Content

---

## D. Content Type Filters

Must support:

- Reels
- Stories
- Carousel
- Hero Shoot
- Fast Content
- BTS
- Styling
- Arrivals
- Viral
- Authority

---

## E. City Logic Filters

Must support:

- Simferopol
- Yalta
- Both

Important:

City is:

```md
mood logic
```

NOT separate media systems.

---

## F. DNA Filters

Must support:

- Classic
- Dramatic
- Romantic
- Naturalistic

---

# CONTENT CARD STRUCTURE

Each content card must contain:

- content title
- hook
- AIDA stage
- content type
- platform
- city mood
- DNA
- CTA
- production requirements
- assigned people
- source assets
- approval status
- publish date
- analytics snapshot
- linked campaign
- linked CRM flow

---

# REQUIRED UI ACTIONS

- duplicate content
- attach assets
- attach references
- create production task
- send to approval
- connect to CRM
- connect to campaign
- archive
- compare performance

---

# 3.3 PERSONAL MEDIA BOARD

## Purpose

Manage Elena personal media.

Focus:

- attention
- authority
- viral layer
- backstage
- personal brand

---

# MAIN SECTIONS

## A. Viral Opportunities

Shows:

- trending themes
- emotional triggers
- hooks
- audience pain points

---

## B. Authority Layer

Shows:

- expertise content
- business observations
- style logic
- opinion content

---

## C. Bridge to GLAME

Tracks:

- transitions to GLAME
- app mentions
- store mentions
- styling mentions

---

## D. Personal Storylines

Tracks recurring content arcs.

Examples:

- building GLAME
- fashion retail in Crimea
- selection logic
- premium retail creation

---

# 3.4 CRM BOARD

## Purpose

Central CRM & retention management.

---

# MAIN SECTIONS

## A. Segment Dashboard

Must show:

- VIP
- active
- inactive
- new
- men
- frequent buyers
- app users
- saved-but-not-purchased

---

## B. CRM Flow Pipeline

Columns:

```md
Idea
Segmented
Drafted
Needs Approval
Approved
Scheduled
Sent
Measured
Optimized
```

---

## C. Return Flow Tracker

Tracks:

- abandoned styling
- inactive customers
- saved selections
- VIP reminders
- event reminders

---

## D. CRM Performance Layer

Shows:

- open rate
- click rate
- return rate
- visit rate
- purchase rate
- unsubscribe risk

---

# CRM CARD STRUCTURE

Must contain:

- segment
- objective
- trigger
- channel
- message
- approval status
- send date
- linked campaign
- linked product focus
- analytics

---

# 3.5 PARTNERSHIP BOARD

## Purpose

Manage:

- collabs
- PR
- external traffic
- events
- influencer ecosystem

---

# MAIN SECTIONS

## A. Partnership Pipeline

Columns:

```md
Identified
Researching
Outreach
Negotiation
Approved
Planned
Executed
Measured
```

---

## B. Partner Categories

Must support:

- hotels
- restaurants
- beauty
- bridal
- influencers
- photographers
- events
- fashion community

---

## C. Collab Content Tracker

Tracks:

- shoots
- stories
- posts
- PR coverage
- traffic outcomes

---

# PARTNERSHIP CARD STRUCTURE

Must contain:

- partner name
- category
- audience fit
- campaign fit
- collab format
- status
- responsible person
- content plan
- expected outcome
- analytics

---

# 3.6 TRAFFIC & GROWTH BOARD

## Purpose

Manage:

- amplification
- growth
- geo traffic
- retarget
- app return
- Yandex ecosystem

---

# MAIN SECTIONS

## A. Active Growth Campaigns

Tracks:

- traffic source
- audience
- city
- objective
- budget
- KPI

---

## B. Amplification Recommendations

Shows:

- high-performing content
- suggested amplification
- expected result

---

## C. App Return Layer

Tracks:

- push ideas
- CRM return logic
- retarget logic
- app save return

---

# GROWTH CARD STRUCTURE

Must contain:

- campaign objective
- source
- target audience
- city
- content asset
- KPI
- status
- analytics

---

# 3.7 PRODUCT FOCUS BOARD

## Purpose

Connect:

- assortment
- sales
- styling
- content
- CRM

---

# MAIN SECTIONS

## A. Product Focus Strip

Shows:

- arrivals
- high-potential products
- slow movers
- seasonal focus

---

## B. Styling Combination Layer

Shows:

- combinations
- mix recommendations
- DNA pairing
- look building

---

## C. Availability Layer

Shows:

- city availability
- stock risks
- replenishment needs

---

# PRODUCT CARD STRUCTURE

Must contain:

- product group
- brand
- city availability
- styling logic
- campaign fit
- CRM fit
- content fit
- sales analytics
- stock status

---

# 3.8 ANALYTICS BOARD

## Purpose

Unified business intelligence layer.

---

# MAIN SECTIONS

## A. Executive Dashboard

Shows:

- traffic
- revenue
- saves
- CRM activity
- app activity
- conversion trends

---

## B. Cross-System Correlations

Examples:

- Reels vs traffic
- app saves vs CRM return
- collabs vs visits
- arrivals vs sales

---

## C. Alerts Layer

Shows:

- anomalies
- failures
- drops
- spikes
- blocked workflows

---

## D. Recommendation Layer

AI-generated recommendations.

---

# 4. GLOBAL TASK OBJECT

All boards use unified task object.

---

# TASK STRUCTURE

Each task must contain:

```json
{
  "task_id": "uuid",
  "title": "string",
  "description": "string",
  "priority": "P0-P3",
  "status": "status",
  "assigned_agent": "agent",
  "assigned_human": "optional",
  "deadline": "datetime",
  "campaign": "optional",
  "city": "optional",
  "DNA": "optional",
  "approval_status": "optional",
  "dependencies": [],
  "analytics": {},
  "attachments": [],
  "result": "optional",
  "next_step": "optional"
}
```

---

# 5. APPROVAL UI SYSTEM

## Approval Queue Must Include

- object preview
- priority
- requesting agent
- deadline
- approve button
- reject button
- revise button
- comments
- escalation warning

---

# APPROVAL COLORS

Suggested:

- green = approved
- yellow = needs review
- red = critical
- gray = expired

---

# 6. SYSTEM HEALTH UI

The platform must contain:

```md
System Health Dashboard
```

---

# MUST MONITOR

- integrations
- failed tasks
- inactive agents
- broken workflows
- CRM failures
- analytics failures
- event failures
- approval bottlenecks

---

# HEALTH STATES

```md
Healthy
Warning
Critical
Offline
```

---

# 7. NOTIFICATION SYSTEM

## Required Notifications

- approval required
- deadline soon
- overdue task
- failed workflow
- CRM send failure
- integration failure
- campaign launch
- analytics anomaly

---

# NOTIFICATION CHANNELS

Must support:

- in-app
- Telegram
- WhatsApp
- email

---

# 8. UI DESIGN PRINCIPLES

The UI must feel:

- premium
- calm
- structured
- architectural
- highly readable
- minimal
- intelligent

---

# VISUAL STYLE

Inspired by:

- linear dashboards
- premium SaaS
- editorial systems
- luxury operating panels

Avoid:

- startup chaos
- gaming UI
- overloaded admin panels
- colorful clutter
- Notion-copy interfaces

---

# DESIGN LANGUAGE

Use:

- cold palette
- graphite
- steel
- soft white
- subtle borders
- clean spacing
- strong hierarchy
- minimal shadows

Avoid:

- bright colors
- rounded playful UI
- mass-market visuals
- emoji-heavy interfaces

---

# 9. FINAL PRINCIPLE

The board system must behave as:

```md
Luxury Retail AI Operating System
```

NOT:

- task manager
- social media planner
- kanban clone
- generic CRM dashboard

