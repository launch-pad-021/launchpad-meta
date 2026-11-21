# Human setup status

The owner marks completed items with a lowercase `x`. Record only completion here.
The setup instructions and permission scopes are in [Developer One-Time Setup](../specs/16-human-setup.md).
Headings give the first readiness gate. Pending items are visible from Step −1.

## A0 · GitHub setup and automated workflows

- [ ] ACCOUNT-05: Create the Telegram bot and retain its token and chat identifier privately.
- [ ] ACCOUNT-06: Set up the agent provider credential.
- [x] GITHUB-01: Create the organization and decide repository visibility.
- [ ] GITHUB-02: Configure an emergency administrator with two-factor authentication and restrict daily-account bypass.
- [ ] GITHUB-APPS-01: Configure the four private organization-owned Apps, their scoped installations, webhooks and dashboard sign-in.
- [ ] GITHUB-SECRETS-01: Configure the repository-scoped organization secrets for agents, Apps and notifications.
- [ ] GITHUB-VARS-01: Configure the organization variables for agent operation, budget, ownership and domain.
- [x] GITHUB-REPOS-01: Create both control repositories and seed their contents.
- [ ] GITHUB-PROJECT-01: Configure the organization Project fields and statuses.

## M0 · After A0 acceptance, before the automated pipeline

- [ ] GITHUB-REPOS-02: After A0-08 lands, run the repository creation script and apply rulesets and owners.
- [ ] FINAL-01: Enable agents at autonomy phase P0 with owner merges.
- [ ] FINAL-02: Follow the kickoff guide for the transition to the pipeline.

## M0 · M0-01 host provisioning and bootstrap

- [ ] ACCOUNT-02: Provision the specified Oracle Cloud account, region, VM, boot volume and restricted ingress.
- [ ] SERVER-01: Review and run the merged infrastructure host bootstrap on the server.

## M0 · M0-02 server secrets and credential prerequisites

- [ ] ACCOUNT-01: Register the domain and delegate DNS to Cloudflare.
- [ ] ACCOUNT-03: Provision the Cloudflare R2 backup bucket and its bucket-scoped access key (backup jobs begin at M0-06).
- [ ] ACCOUNT-04: Create the MaxMind account and obtain the GeoLite2 license key.
- [ ] DNS-02: Create the zone-scoped DNS token and retain it for server secret provisioning.
- [ ] SERVER-02: Install server secret files and back up the age identity in the password manager.

## M0 · M0-03 routing and certificates

- [ ] DNS-01: Configure the required DNS-only records for the server.

## M0 · M0-05 infrastructure synchronization

- [ ] SERVER-03: Install the read-only deploy key and status token and enable the infrastructure synchronization timer.
