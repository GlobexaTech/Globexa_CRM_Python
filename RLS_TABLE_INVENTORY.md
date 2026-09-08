# RLS table inventory

Generated from SQLAlchemy metadata; CI compares this model inventory to PostgreSQL RLS flags.

- `activities`
- `agent_definitions`
- `ai_usage_logs`
- `attribution_rules`
- `audit_logs`
- `campaign_audiences`
- `campaign_recipients`
- `campaign_sequences`
- `campaign_stats`
- `campaign_templates`
- `campaign_triggers`
- `campaigns`
- `companies`
- `contacts`
- `conversations`
- `deals`
- `domain_events`
- `email_events`
- `email_provider_configs`
- `event_deliveries`
- `feature_entitlements`
- `icp_profiles`
- `integration_credentials`
- `integration_sync_logs`
- `integrations`
- `lead_source_configs`
- `leads`
- `memberships`
- `messages`
- `notes`
- `oauth_tokens`
- `pending_leads`
- `pipelines`
- `products`
- `proposal_templates`
- `proposals`
- `revenue_attributions`
- `sending_domains`
- `stages`
- `subscriptions`
- `suppression_lists`
- `tasks`
- `touchpoints`
- `usage_records`
- `webhook_endpoints`
- `webhook_receipts`
- `workflow_actions`
- `workflow_conditions`
- `workflow_execution_logs`
- `workflow_triggers`
- `workflows`

51 tenant_id tables. Shared identities/workspaces also protected: `users`, `tenants` (53 total).

Global catalogs: `plans`, `features`, `plan_features`. Global pre-tenant authentication audit: `security_events` (runtime INSERT only). Roles and permissions are a code catalog.
