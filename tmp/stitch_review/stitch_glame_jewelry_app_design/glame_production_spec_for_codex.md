# GLAME App — Final Production Specifications for Codex

## 1. Brand Identity & Visual Language
*   **Style**: Architectural Minimalism.
*   **Geometry**: Radius `0px`, Border `1px` (Color: `#5C6064`).
*   **Palette**: Graphite (`#222426`), Near Black (`#0E1012`), Steel Gray (`#8E9397`), Cold Light Gray (`#C7CBCF`), White (`#EFF1F2`).
*   **Typography**: Clinica Pro Regular (Main asset).
    *   Line-height: 1.35–1.45 for body/descriptions.
    *   No negative letter-spacing.
*   **Logo/Sign**: Use ONLY approved original assets from the inventory.

## 2. Navigation & Layout System (Safe Area)
*   **Top Bar**: Transparent overlay for Hero slides; solid for internal screens.
    *   Logo: Centered.
    *   Search: Right.
    *   Offset: `safeAreaTop + 12–16px`.
*   **Bottom Nav**: 
    *   Visible Height: `96px`.
    *   Total Reserve: `130px` (including `34px` Safe Area bottom).
    *   Content Air: `16–24px` above the bottom bar.
*   **CTA Zone**: Fixed coordinates for Hero carousel slides to prevent jumping.

## 3. Core Screens Index (30+ Approved Screens)
*   **Storefront**: Home (6 Blocks), Catalog, Filters, Product Detail.
*   **Discovery**: Brands List, Brand Detail (Geometry), Spaces (Yalta/Simferopol).
*   **Personalization**: My Style, Look-feed, Look Builder, AI Photo Selection Flow, Stylist Chat.
*   **Commerce**: Cart, Checkout Steps (1-4), Order Confirmation.
*   **Account**: Profile, Orders History, Loyalty Progress.
*   **Auth**: Welcome/Onboarding, Login, Register, OTP Confirmation.

## 4. Technical Logic
*   **Auth Gates**: Required for photo upload, stylist chat, profile, and checkout.
*   **Stylist Status**: Calculated by Moscow time (10:00–20:00).
*   **Image Integrity**: No AI-generation for real spaces or brand assets.

## 5. Assets Reference
*   Logo: {{DATA:IMAGE:IMAGE_7}} (Black), {{DATA:IMAGE:IMAGE_10}} (Silver).
*   G-Sign: {{DATA:IMAGE:IMAGE_11}}.
*   Home Layout Spec: {{DATA:DOCUMENT:DOCUMENT_96}}.
*   Identity Rules: {{DATA:DOCUMENT:DOCUMENT_35}}.
