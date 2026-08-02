# Doctor Final Accessibility Review

Target: WCAG 2.1 AA for Doctor workflow.

Automated coverage uses Axe tags `wcag2a`, `wcag2aa`, and `wcag21aa` across desktop and mobile Playwright projects. Phase suites cover dashboard, availability, queue, workspace, records, messages, notifications, reviews, profile, privacy, and explicit intake deep route.

Manual review checklist:

- Logical heading order and one page-level heading.
- Keyboard-visible controls, dialogs, tabs, filters, and destructive confirmations.
- Named landmarks, form labels, live status/error feedback, and focus return after dialogs.
- Responsive operation at mobile project viewport without clipped actions.
- English LTR plus Arabic and Central Kurdish RTL layout.
- Status not conveyed by color alone.

## Evidence

- Full Playwright: 184 passed, 2 desktop-only mobile-interaction skips, 0 failed. Skipped interactions passed in mobile project.
- Doctor Phase E intake deep route passed Axe on mobile and desktop.
- Doctor Phase A-E suites cover EN, AR, CKB, LTR/RTL, focus, semantic navigation, and responsive workflows.
- AccessLint CLI was available through `npx`: CLI 0.12, engine 0.16. Authenticated Doctor pages cannot be seeded/authenticated through that CLI, so Axe provides authoritative scoped automation.
- AccessLint public landing scan with `--wait-for main` reported 16 issues: contrast, nested interactive/duplicate ARIA, and heading-order findings. Public landing page is outside Doctor Phase E and was not modified.

Final result: Doctor workflow accessibility passed within stated scope. Public landing findings remain out of scope and documented.
