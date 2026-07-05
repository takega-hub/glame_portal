---
name: Architectural Minimalist
colors:
  surface: '#121416'
  surface-dim: '#121416'
  surface-bright: '#38393c'
  surface-container-lowest: '#0c0e10'
  surface-container-low: '#1a1c1e'
  surface-container: '#1e2022'
  surface-container-high: '#282a2c'
  surface-container-highest: '#333537'
  on-surface: '#e2e2e5'
  on-surface-variant: '#c4c7c8'
  inverse-surface: '#e2e2e5'
  inverse-on-surface: '#2f3133'
  outline: '#8e9192'
  outline-variant: '#434749'
  surface-tint: '#c4c7c8'
  primary: '#ffffff'
  on-primary: '#2e3132'
  primary-container: '#e1e3e4'
  on-primary-container: '#626566'
  inverse-primary: '#5c5f60'
  secondary: '#c6c6c9'
  on-secondary: '#2f3133'
  secondary-container: '#454749'
  on-secondary-container: '#b4b5b7'
  tertiary: '#ffffff'
  on-tertiary: '#2c3134'
  tertiary-container: '#dee3e7'
  on-tertiary-container: '#606569'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#e1e3e4'
  primary-fixed-dim: '#c4c7c8'
  on-primary-fixed: '#191c1d'
  on-primary-fixed-variant: '#444748'
  secondary-fixed: '#e2e2e5'
  secondary-fixed-dim: '#c6c6c9'
  on-secondary-fixed: '#1a1c1e'
  on-secondary-fixed-variant: '#454749'
  tertiary-fixed: '#dee3e7'
  tertiary-fixed-dim: '#c2c7cb'
  on-tertiary-fixed: '#171c1f'
  on-tertiary-fixed-variant: '#42474b'
  background: '#121416'
  on-background: '#e2e2e5'
  surface-variant: '#333537'
  cold-light-gray: '#C7CBCF'
  border-gray: '#5C6064'
  soft-gray: '#D8DADB'
typography:
  display-lg:
    fontFamily: Hanken Grotesk
    fontSize: 48px
    fontWeight: '400'
    lineHeight: 56px
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Hanken Grotesk
    fontSize: 32px
    fontWeight: '500'
    lineHeight: 40px
    letterSpacing: 0em
  headline-lg-mobile:
    fontFamily: Hanken Grotesk
    fontSize: 24px
    fontWeight: '500'
    lineHeight: 32px
  body-lg:
    fontFamily: Hanken Grotesk
    fontSize: 18px
    fontWeight: '400'
    lineHeight: 28px
  body-md:
    fontFamily: Hanken Grotesk
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  label-md:
    fontFamily: Hanken Grotesk
    fontSize: 14px
    fontWeight: '600'
    lineHeight: 20px
    letterSpacing: 0.05em
  label-sm:
    fontFamily: Hanken Grotesk
    fontSize: 12px
    fontWeight: '500'
    lineHeight: 16px
    letterSpacing: 0.05em
spacing:
  page-padding-h: 28px
  button-gap: 16px
  bottom-nav-height: 96px
  top-bar-height: 56px
  safe-air-bottom: 24px
  grid-gutter: 1px
---

## Brand & Style

The design system is a premium digital expression of high-end architectural space. It evokes the sensory qualities of concrete, glass, and brushed metal through a cold, disciplined color palette and rigorous geometric precision. The target audience seeks a luxury experience that prioritizes clarity, structural integrity, and spatial "air" over decorative trends.

The aesthetic follows a **Minimalist-Architectural** movement:
- **Atmosphere:** Cold, technical, and expansive.
- **Negative Constraints:** Strictly no rounded corners (0px radius), no warm tones (beige/gold), and no soft "marketplace" shadows.
- **Visual Identity:** All layouts must respect the original GLAME logo and G-sign assets. These are fixed structural elements that cannot be redrawn or modified.
- **Materiality:** Photography should emphasize real architectural textures, treated with cool color correction to maintain the system's "premium digital space" narrative.

## Colors

The palette is strictly achromatic and cold, designed to mimic structural materials. The default mode is **Dark**, utilizing depth through tonal layering rather than shadows.

- **Primary (White):** Used for high-impact typography and primary CTA backgrounds to contrast against dark environments.
- **Secondary (Graphite):** The core surface color for primary UI containers and text on light backgrounds.
- **Tertiary (Steel Gray):** Used for secondary text, metadata, and inactive states.
- **Neutral (Near Black):** The base canvas color, representing deep architectural shadow.
- **Border Gray:** A functional color used for the mandatory 1px structural outlines that define the UI grid.

## Typography

The design system uses a clean, architectural sans-serif (Hanken Grotesk as a proxy for Clinica Pro) to maintain a technical and sophisticated tone. 

- **Weight & Contrast:** Typography relies on weight shifts and uppercase styling for hierarchy rather than decorative flourishes.
- **Clarity:** Labels and UI elements utilize increased letter spacing and uppercase styling to evoke a "gallery" or "blueprint" feel.
- **Scaling:** Headlines are scaled down for mobile to ensure structural integrity and prevent awkward wrapping in tight architectural grids.
- **Logo Integrity:** The GLAME wordmark and G-sign are image assets and must never be substituted with live text.

## Layout & Spacing

This design system utilizes a **Fixed Grid** philosophy based on proportion and structural "zones." The layout is defined by physical boundaries and safe areas.

- **Horizontal Rhythm:** A consistent 28px horizontal padding is applied to all main content to ensure readability and "air" on mobile devices (roughly 7% of screen width).
- **Vertical Zones:** 
    - **Top Bar:** Fixed 56px height, typically a transparent overlay to allow background photography to bleed into the status bar area.
    - **Bottom Nav:** A substantial 96px visible height to ground the UI.
    - **Safe Zones:** Content must respect a "Hero Content Safe Zone" that clears both top and bottom navigation bars with an additional 16-24px of "air."
- **Structural Lines:** Elements are separated by a 1px "Border Gray" line, creating a wireframe-like clarity across the interface.

## Elevation & Depth

Hierarchy is achieved through **Structural Outlines** and **Tonal Layering** rather than traditional shadows.

- **Flat Depth:** All elements exist on a single flat plane or within defined containers. 
- **Borders as Depth:** 1px solid borders (`#5C6064`) define the physical limits of every component (cards, buttons, tiles). 
- **No Shadows:** Shadows are strictly prohibited to maintain the "concrete and metal" architectural aesthetic. 
- **Transparency:** Backgrounds in the top navigation use transparency to create a sense of glass and light, allowing the architectural photography of the hero section to provide the visual foundation.

## Shapes

The shape language is **Strictly Linear**. 

- **Radius:** All corners are set to 0px. This applies to buttons, input fields, cards, and image containers. 
- **Geometry:** Every element must appear as if cut from sheets of metal or stone. 
- **Borders:** A consistent 1px border is the primary decorative and functional tool for defining shape.

## Components

### Buttons
- **Primary:** 56px height, minimum 300px width. Solid White (`#EFF1F2`) fill with Graphite (`#222426`) text. Sharp 0px corners.
- **Secondary:** 56px height. Transparent fill with 1px White border and White text.
- **Pill Restriction:** Pill-shaped buttons are strictly forbidden.

### Navigation
- **Top Bar:** Centered logo asset. Search icon on the right. Cart icon only appears when active.
- **Bottom Nav:** Fixed 96px height. The "G-sign" asset is used for the active state. Inactive states use approved minimalist line icons.

### Tiles & Cards
- **Service Tiles:** Arranged in a 2x2 grid. 1px borders. Information is structured vertically: Number (top), Title (middle), Description (bottom).
- **Action Panels:** Full-width panels with 1px top/bottom borders. Features a number column on the left and a chevron on the right.

### Input Fields
- Underlined or fully boxed with 1px borders. No background fills in dark mode. Typography follows the Label-MD spec for placeholders.

### Feedback & Indicators
- **Slide Indicators:** Simple geometric dots or lines positioned at least 16px above the bottom navigation bar.