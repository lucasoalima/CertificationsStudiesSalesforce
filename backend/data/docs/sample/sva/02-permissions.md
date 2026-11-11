# Sharing and Visibility: permissions to objects and fields (study notes)

## Profiles and permission sets
Object permissions (CRUD, View All, Modify All) and field-level security control what a user can do with an object and its fields; the sharing model controls which records. Permission sets add permissions on top of the profile; they never remove them. Salesforce recommends minimum-access profiles and permission sets or permission set groups for everything else.

## Permission set groups and muting
A permission set group bundles permission sets for a persona. A muting permission set inside a group removes specific permissions that the other sets in the group would grant, for example removing Delete on Opportunity for interns without creating a new profile.

## Field-level security
To hide a field from some users who share the same profile, remove read access from the profile and grant it through a permission set only to the users who need it. Page layouts only hide fields from the UI; field-level security protects the field in reports, list views and the API.

## View All and Modify All
View All and Modify All on an object bypass the sharing model for that object. View All Data and Modify All Data do the same for every object and should be limited to administrators.

## Custom permissions
Custom permissions let code, validation rules and flows check whether a user has a capability, for example bypassing a validation rule for an integration user, without hard-coding profile names.
