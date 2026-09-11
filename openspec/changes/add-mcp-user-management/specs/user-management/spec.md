## Purpose

Viewing and modifying accounts that already exist: an administrative listing of accounts and
their signup countries, an administrative password change for any named account, and a
self-service password change for the caller's own account.

## ADDED Requirements

### Requirement: List accounts
The system SHALL return a listing of accounts, each entry carrying that account's username,
the country recorded at signup, and the date the account was created.

#### Scenario: Successful listing
- **WHEN** an administrator requests the account listing
- **THEN** the response is HTTP 200 and carries one entry per account, each with a username, a
  country, and a signup date

### Requirement: Require administrative privileges to list accounts
The system SHALL refuse an account listing to a caller who is not an administrator, and to a
caller who presents no valid authentication token.

#### Scenario: Unauthenticated caller
- **WHEN** the account listing is requested with no valid authentication token
- **THEN** the request is refused and no account data is returned

#### Scenario: Authenticated but non-administrative caller
- **WHEN** the account listing is requested by an authenticated caller who is not an
  administrator
- **THEN** the request is refused and no account data is returned

### Requirement: Filter the account listing by country
The system SHALL restrict the listing to accounts whose recorded country matches a supplied
country, compared without regard to case.

#### Scenario: Filtering to a country
- **WHEN** the listing is requested for a country that some accounts recorded at signup
- **THEN** only accounts recording that country are returned

#### Scenario: Country differing only in case
- **WHEN** the listing is requested for a country whose case differs from the recorded value
- **THEN** the same accounts are returned as for the recorded case

### Requirement: Filter the account listing by username
The system SHALL restrict the listing to accounts whose username matches a supplied username,
compared without regard to case.

#### Scenario: Filtering to a username
- **WHEN** the listing is requested for a username that exists
- **THEN** only that account is returned

#### Scenario: Username differing only in case
- **WHEN** the listing is requested for a username whose case differs from the stored value
- **THEN** the same account is returned as for the stored case

### Requirement: Include accounts with no recorded country
The listing SHALL include accounts that have no country recorded against them, reporting the
country as empty rather than omitting the account. An account created outside signup has no
recorded country, and an administrative listing that silently omitted such accounts would
misrepresent who exists.

#### Scenario: An account created outside signup
- **WHEN** the unfiltered listing is requested and an account exists that never recorded a
  country
- **THEN** that account appears in the listing with an empty country

### Requirement: Never disclose an email address or an internal identifier in a listing
No entry in the account listing SHALL carry an email address or any internal record
identifier, whether the listing is filtered or not.

#### Scenario: Unfiltered listing
- **WHEN** the unfiltered listing is returned
- **THEN** no entry carries an email address or an internal record identifier

#### Scenario: Filtered listing
- **WHEN** a listing filtered by country or by username is returned
- **THEN** no entry carries an email address or an internal record identifier

### Requirement: Change any account's password as an administrator
The system SHALL let an administrator set a new password on any named account without
supplying that account's current password.

#### Scenario: Administrator changes another account's password
- **WHEN** an administrator submits a valid new password for a named account
- **THEN** the response is HTTP 200 and the account thereafter authenticates with the new
  password and not the old one

### Requirement: Require administrative privileges to change another account's password
The system SHALL refuse a password change aimed at an account other than the caller's own
unless the caller is an administrator, and SHALL refuse it entirely to a caller presenting no
valid authentication token.

#### Scenario: Authenticated but non-administrative caller
- **WHEN** an authenticated caller who is not an administrator submits a new password for
  another account
- **THEN** the request is refused and that account's password is unchanged

#### Scenario: Unauthenticated caller
- **WHEN** a caller presenting no valid authentication token submits a new password for a
  named account
- **THEN** the request is refused and that account's password is unchanged

### Requirement: Resolve the named account without regard to case
An administrative password change SHALL find the named account without regard to case, and
SHALL refuse the request rather than choose between accounts when more than one matches. The
account listing matches usernames without regard to case, so an account named from a listing
must be reachable in the case the listing reported.

#### Scenario: Name differing only in case
- **WHEN** an administrator submits a new password for an account named in a different case
  from the stored username
- **THEN** that account's password is changed

#### Scenario: More than one account matches the name
- **WHEN** an administrator submits a new password for a name that matches more than one
  account
- **THEN** the request is refused and no account's password is changed

### Requirement: Reject a password change for an unknown account
The system SHALL refuse an administrative password change naming an account that does not
exist.

#### Scenario: Unknown account
- **WHEN** an administrator submits a new password for a name matching no account
- **THEN** the request is refused

### Requirement: Change one's own password
The system SHALL let an authenticated caller replace their own password by supplying both
their current password and a new one.

#### Scenario: Correct current password
- **WHEN** an authenticated caller submits their correct current password and a valid new one
- **THEN** the response is HTTP 200 and the account thereafter authenticates with the new
  password and not the old one

#### Scenario: Unauthenticated caller
- **WHEN** a caller presenting no valid authentication token submits a self-service password
  change
- **THEN** the request is refused

### Requirement: Refuse a self-service change without the correct current password
The system SHALL refuse a self-service password change whose supplied current password is not
the account's current password, and SHALL leave the password unchanged. Possession of a valid
authentication token alone SHALL NOT be sufficient to replace a password.

#### Scenario: Wrong current password
- **WHEN** an authenticated caller submits a current password that is not their own, together
  with a valid new password
- **THEN** the request is refused and the account still authenticates with its existing
  password

### Requirement: Hold a changed password to the signup strength rules
A new password supplied to either password change SHALL be subject to the same strength rules
the system applies when an account is created, including the maximum length.

#### Scenario: New password below the strength rules
- **WHEN** either password change is submitted with a new password that signup would have
  rejected as too short, or as lacking a letter or a digit
- **THEN** the request is refused and the account still authenticates with its existing
  password

#### Scenario: New password above the maximum length
- **WHEN** either password change is submitted with a new password longer than the maximum
  signup permits
- **THEN** the request is refused, the message states the maximum, and the account still
  authenticates with its existing password

### Requirement: Invalidate existing authentication tokens on a password change
A successful password change SHALL invalidate every authentication token already issued for
the account whose password changed.

#### Scenario: Administrative change
- **WHEN** an administrator changes an account's password
- **THEN** an authentication token issued to that account before the change is no longer
  accepted

#### Scenario: Self-service change
- **WHEN** a caller changes their own password
- **THEN** an authentication token issued to that caller before the change is no longer
  accepted

### Requirement: Never return a password
No response to either password change SHALL contain a submitted password, whether the request
succeeded or was refused.

#### Scenario: Successful change
- **WHEN** a password change succeeds
- **THEN** the response body contains no submitted password

#### Scenario: Refused change
- **WHEN** a password change is refused for any reason
- **THEN** the response body contains no submitted password
