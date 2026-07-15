// MVP runs a single tenant. The Tenant model exists so a future, separately
// operated Trainer-Portal instance (see docs/ARCHITEKTUR.md, Abschnitt 6)
// can reuse the same schema without a migration.
export const DEFAULT_TENANT_ID = "golfbox";
