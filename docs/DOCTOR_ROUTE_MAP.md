# Doctor Phase D route map

Final navigation order: Dashboard, Consultations, Messages, Medical Records, Reviews, Availability, Notifications, Profile, Privacy.

Frontend roots: `/app/doctor`, `/consultations`, `/messages`, `/medical-records`, `/reviews`, `/availability`, `/notifications`, `/profile`, `/privacy` under doctor root. Privacy children: `/privacy/exports`, `/privacy/deletion`. Conversation: `/messages/:consultationId`.

Shared `/app/profile`, `/app/notifications`, `/app/privacy`, `/app/privacy/exports`, and `/app/privacy/deletion` redirect by role. Doctor targets doctor pages; patient targets patient pages; staff retains staff behavior. Redirect destinations never point back to shared route.
