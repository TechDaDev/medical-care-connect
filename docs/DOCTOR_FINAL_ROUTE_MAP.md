# Doctor Final Route Map

| Navigation | Frontend route | Backend authority |
| --- | --- | --- |
| Dashboard | `/app/doctor` | `/api/doctors/me/dashboard/` |
| Consultations | `/app/doctor/consultations` | `/api/consultations/doctor/` |
| Workspace | `/app/doctor/consultations/:consultationId` | `/api/consultations/:id/doctor/` |
| Intake | `/app/doctor/consultations/:consultationId/intake` | `/api/consultations/:id/doctor-intake/` |
| Messages | `/app/doctor/messages` | `/api/doctors/me/message-threads/` |
| Thread | `/app/doctor/messages/:consultationId` | `/api/messaging/:id/messages/` |
| Medical records | `/app/doctor/medical-records` | `/api/doctors/me/medical-records/` |
| Record | `/app/doctor/medical-records/:recordId` | `/api/doctors/me/medical-records/:id/` |
| Reviews | `/app/doctor/reviews` | `/api/doctors/me/reviews/` |
| Availability | `/app/doctor/availability` | `/api/doctors/me/availability/` |
| Notifications | `/app/doctor/notifications` | `/api/doctors/me/notifications/` |
| Profile | `/app/doctor/profile` | `/api/doctors/me/` |
| Privacy | `/app/doctor/privacy` | `/api/doctors/me/privacy/` |
| Privacy exports | `/app/doctor/privacy/exports` | `/api/doctors/me/privacy/exports/` |
| Privacy deletion | `/app/doctor/privacy/deletion` | `/api/doctors/me/privacy/deletion/` |

Required navigation order: Dashboard, Consultations, Messages, Medical Records, Reviews, Availability, Notifications, Profile, Privacy.
