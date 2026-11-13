# Example — Security Assessment (Mode C)

**Prompt (Spanish, to show bilingual behavior):**

> Revisa el modelo de autenticación y autorización de esta API contra el OWASP API Security Top 10.
> Solo análisis estático; no tenemos entorno de pruebas aprobado.

**Input:** the same sample service used in
[`../repository-review-example/sample-app/`](../repository-review-example/sample-app/).

**Output:** [`security-report.md`](security-report.md), following `assets/security-report.md`.

**What this example demonstrates**

- Authentication and authorization evaluated separately ("authentication ≠ authorization").
- JWT checklist with Verified / Not located status per control, and a library-version caveat instead
  of an assumed vulnerability.
- Every OWASP API Top 10 (2023) category marked as finding, "no issue found in scope" or
  "not assessed" — never silently skipped.
- Secrets reported by location and type only.
- Verification methods that are non-destructive and require an approved environment.
- Spanish narrative with technical identifiers kept in English.
