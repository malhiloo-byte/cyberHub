# CyberOS Frontend Direction

## Three initial approaches

### Theme Name: Obsidian Command Center
**Very Brief Intro:** A dark, editorial security operations environment with graphite surfaces, brass highlights, and sharp data hierarchy. It feels deliberate, private, and built for serious operators.
**Probability:** 0.07

### Theme Name: Arctic Signal Desk
**Very Brief Intro:** A high-key technical workspace using cold paper, blue-black ink, and signal orange for action states. It feels precise, calm, and research-oriented.
**Probability:** 0.03

### Theme Name: Mineral Atelier
**Very Brief Intro:** A warm premium interface with stone, ink, and restrained copper accents, treating security telemetry like a carefully edited field journal. It feels crafted, human, and quietly confident.
**Probability:** 0.09

## Chosen approach: Obsidian Command Center

### Design Movement

Editorial Swiss International Style fused with luxury industrial design: strict typographic rhythm, asymmetric composition, dense but breathable information, and materials that feel like smoked glass, anodized metal, and archival paper.

### Core Principles

1. **Command, not decoration:** every surface communicates system state or provides a clear next action.
2. **Quiet luxury:** depth comes from material contrast, hairline borders, restrained brass, and typography—not gradients or ornamental noise.
3. **Asymmetric authority:** the sidebar anchors the system while the content field uses offset cards, editorial labels, and deliberate negative space.
4. **Evidence-first clarity:** status, authorization, scope, and execution provenance stay visible at a glance.

### Color Philosophy

Obsidian black and graphite create privacy and operational focus. Bone-white typography preserves editorial clarity. Aged brass is the ownable brand signal for trusted authority, while signal teal and controlled vermilion are reserved for system state. No purple gradients, no generic neon, and no decorative glow.

### Layout Paradigm

Persistent left rail, compact utility bar, and a wide asymmetric command canvas. The hero is an operational briefing rather than a centered marketing block. Large metrics sit beside a live authorization brief; lower sections alternate between dense tables and open breathing zones.

### Signature Elements

The interface repeats a slim brass vertical rule, numbered section markers, and a “signal stamp” treatment for authorization and execution state. Cards use varied radii: mostly sharp editorial corners with only small utility controls softened.

### Interaction Philosophy

Interactions feel like operating a precision instrument: immediate feedback, clear focus rings, no surprise motion, and transitions that expose state rather than entertain. Destructive or security-sensitive actions require explicit confirmation language.

### Animation

Use 160–220ms ease-out transitions for hover, focus, and panel entry. Stagger dashboard sections by 40ms only on first load. Animate opacity and transform only. Respect reduced motion and keep keyboard navigation instant.

### Typography System

Use **DM Sans** for interface text and **IBM Plex Mono** for identifiers, timestamps, command strings, and evidence metadata. Headlines use tight, editorial tracking with sentence case. Labels use uppercase mono at 0.12em tracking. Never use Inter.

### Brand Essence

**CyberOS is a private command layer for people building real cybersecurity capability—turning scope, evidence, execution, and learning into one auditable operating surface.** Personality: disciplined, exacting, quietly ambitious.

### Brand Voice

Headlines are direct and operational. CTAs name the consequence and the boundary. Microcopy explains why an action is safe or blocked.

> “Your authorization boundary is the product.”

> “No execution without evidence of scope.”

### Wordmark & Logo

The wordmark uses a custom split-bar “C” monogram: a squared orbital bracket interrupted by a single brass signal line. The mark is geometric, text-free, and works as a compact rail emblem and favicon.

### Signature Brand Color

**Aged Brass — `#C8A96B`**. It signals earned authority, not decoration, and appears only in active navigation, trusted scope state, and key data accents.

## Style Decisions

- The primary mark is always the squared orbital bracket with one aged-brass signal interruption; the generic diamond emblem is rejected.
- Aged Brass `#C8A96B` is reserved for active navigation, authorization state, section rules, key numerals, and trusted-scope accents.
- CTAs must state the operational boundary or consequence, such as “Review scope before execution” and “Queue authorized task.”
