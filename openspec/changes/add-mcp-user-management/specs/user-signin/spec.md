## ADDED Requirements

### Requirement: Sign in with a verified Google access token
The system SHALL accept a Google access token obtained by the caller elsewhere, and on
accepting it SHALL return the same authentication token an email-and-password signin returns.
The system SHALL verify the token with Google rather than completing the Google login itself,
and SHALL never require or hold a Google client secret.

#### Scenario: Valid token for a matching account
- **WHEN** a Google access token is submitted that Google recognises, whose audience is a
  configured client id, whose email address is verified, and which matches exactly one account
- **THEN** the response is HTTP 200 with a body of the form `{"token": "<opaque value>"}`

#### Scenario: The same account may sign in repeatedly
- **WHEN** a valid Google access token is submitted twice for the same account
- **THEN** both attempts succeed and each returns a usable authentication token

### Requirement: Accept only a token issued for this application
The system SHALL refuse a Google access token whose audience is not one of the configured
client ids. The configured client ids SHALL be a list, so that further ids can be accepted
without changing behaviour for the existing ones.

#### Scenario: Token issued for another application
- **WHEN** a Google access token is submitted whose audience is not a configured client id
- **THEN** the request is rejected and no authentication token is returned

#### Scenario: A second configured client id
- **WHEN** more than one client id is configured and a Google access token is submitted whose
  audience is any one of them
- **THEN** the token is accepted on that basis

### Requirement: Require a verified email address
The system SHALL refuse a Google access token whose email address Google has not verified.

#### Scenario: Unverified email address
- **WHEN** a Google access token is submitted whose email address is not verified
- **THEN** the request is rejected and no authentication token is returned

### Requirement: Refuse an absent or ambiguous matching account
The system SHALL refuse a Google access token that matches no account, and SHALL refuse one
that matches more than one account rather than choosing between them.

#### Scenario: No matching account
- **WHEN** a verified Google access token is submitted whose email address matches no account
- **THEN** the request is rejected and no authentication token is returned

#### Scenario: More than one matching account
- **WHEN** a verified Google access token is submitted whose email address matches more than
  one account
- **THEN** the request is rejected and no authentication token is returned

### Requirement: Refuse an embargoed account
The system SHALL refuse a Google sign-in for an account an email-and-password signin would
refuse as embargoed.

#### Scenario: Embargoed matching account
- **WHEN** a verified Google access token is submitted that matches exactly one account, and
  that account is embargoed
- **THEN** the request is rejected and no authentication token is returned

### Requirement: Restrict Google sign-in to a configured hosted domain
When a hosted domain is configured, the system SHALL accept only a Google access token that
Google attests belongs to that domain, compared without regard to case. The email address's
own domain SHALL NOT be substituted for that attestation. When no hosted domain is configured,
this restriction SHALL NOT apply.

#### Scenario: Matching hosted domain
- **WHEN** a hosted domain is configured and a token attested to that domain is submitted
- **THEN** the restriction is satisfied and sign-in proceeds

#### Scenario: Hosted domain differing only in case
- **WHEN** a hosted domain is configured and a token attested to the same domain in different
  case is submitted
- **THEN** the restriction is satisfied and sign-in proceeds

#### Scenario: Non-matching hosted domain
- **WHEN** a hosted domain is configured and a token attested to a different domain is
  submitted
- **THEN** the request is rejected and no authentication token is returned

#### Scenario: No hosted-domain attestation
- **WHEN** a hosted domain is configured and a token carrying no hosted-domain attestation is
  submitted
- **THEN** the request is rejected and no authentication token is returned

#### Scenario: No restriction configured
- **WHEN** no hosted domain is configured and a token carrying no hosted-domain attestation is
  otherwise valid
- **THEN** sign-in proceeds

### Requirement: Reject every Google-side refusal identically
Every refusal caused by the token itself - unrecognised by Google, wrong audience, unverified
email, wrong hosted domain, or Google being unreachable - SHALL produce the same status and
the same response body, so the response cannot be used to tell them apart. Every refusal
caused by the account - no match, more than one match, or an embargoed account - SHALL
likewise produce one status and one body, so the response cannot be used to discover which
addresses have accounts.

#### Scenario: Two different token-side refusals
- **WHEN** two Google sign-ins are refused for two different token-side reasons
- **THEN** both responses are identical in status and body

#### Scenario: Two different account-side refusals
- **WHEN** two Google sign-ins are refused for two different account-side reasons
- **THEN** both responses are identical in status and body

### Requirement: Never return a token in a Google sign-in rejection
A rejected Google sign-in SHALL NOT return an authentication token, nor echo the submitted
Google access token, anywhere in its response.

#### Scenario: Rejected response contents
- **WHEN** a Google sign-in is rejected for any reason
- **THEN** the response body contains neither an authentication token nor the submitted Google
  access token

### Requirement: Limit how often Google sign-in may be attempted
The system SHALL cap how many Google sign-in attempts one caller may make in a period, and
SHALL refuse attempts beyond that cap without contacting Google. Google sign-in is
unauthenticated and each attempt causes an outbound request, so an uncapped endpoint lets any
caller generate unbounded outbound traffic.

#### Scenario: Attempts beyond the cap
- **WHEN** one caller makes more Google sign-in attempts in the period than the cap allows
- **THEN** the attempts beyond the cap are refused and no authentication token is returned

#### Scenario: A refused attempt contacts nobody
- **WHEN** an attempt is refused for exceeding the cap
- **THEN** no verification request is made to Google for that attempt
