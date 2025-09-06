# Owner Dashboard Usage Guide

## Overview
The inspection agent system now supports owner-specific dashboards. Each owner can have their own personalized gallery where all their property inspection reports are collected.

## How It Works

### 1. Frontend GUI - Inspector Portal
When using the frontend.py GUI, inspectors can now:
- **Enter Owner ID**: A unique identifier for each property owner (e.g., "john_smith", "ABC_Properties", etc.)
- **Property Address**: Automatically extracted from the ZIP filename
- **Owner Name**: Optional display name for the owner

### 2. Owner ID Field
The new "Owner ID" field in the GUI allows you to:
- Route reports to specific owner dashboards
- Create personalized galleries for each owner
- Leave blank to use the general gallery

### 3. Accessing Owner Dashboards
Once reports are submitted with an Owner ID, owners can access their personalized dashboard at:
```
http://localhost:8000/owner/{owner_id}
```

For example:
- `http://localhost:8000/owner/john_smith` - John Smith's dashboard
- `http://localhost:8000/owner/ABC_Properties` - ABC Properties' dashboard

## Example Usage

### Step 1: Submit Reports with Owner ID
1. Open the Inspector Portal GUI (`python frontend.py`)
2. Add ZIP files containing property photos
3. Enter the Owner ID (e.g., "john_smith")
4. Click "Generate Reports"

### Step 2: Access Owner Dashboard
The owner can now visit their personalized dashboard:
```
http://localhost:8000/owner/john_smith
```

This dashboard will show:
- All properties belonging to this owner
- All inspection reports for each property
- Photo galleries for each inspection
- Critical issues and recommendations

## Owner ID Best Practices

### Recommended Format
- Use lowercase with underscores: `john_smith`, `miami_properties`
- Or use company codes: `ABC001`, `XYZ_CORP`
- Avoid spaces and special characters

### Examples of Good Owner IDs
- `john_smith` - Individual owner
- `abc_properties` - Property management company
- `miami_rentals_001` - Location-based with number
- `customer_12345` - Numbered customer ID

## Technical Details

### How Reports Are Linked
When a report is submitted with an Owner ID:
1. The system creates or updates a client record with the Owner ID
2. The property is linked to this client
3. The report is associated with the property
4. The owner dashboard queries all reports for this client

### API Endpoints
- Dashboard Access: `GET /api/portal/dashboard?portal_token={owner_id}`
- Owner Dashboard Page: `GET /owner/{owner_id}`

## Benefits

1. **Personalized Experience**: Each owner sees only their properties
2. **Easy Access**: Simple URL structure for owners to remember
3. **Centralized Management**: All reports in one place
4. **Privacy**: Each owner's data is separate

## Troubleshooting

### Dashboard Not Found
If you see "Owner dashboard not found", check:
- The Owner ID is spelled correctly
- Reports have been submitted with this Owner ID
- The backend server is running

### No Properties Shown
If the dashboard loads but shows no properties:
- Verify reports were submitted with the correct Owner ID
- Check the database has the client record
- Ensure the --register flag was used when generating reports

## Future Enhancements
- Password protection for owner dashboards
- Email notifications when new reports are added
- Owner self-registration portal
- Report comparison tools