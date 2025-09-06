# Owner Registration & Dashboard Access Guide

## Overview
Property owners can now self-register to receive their personalized inspection gallery dashboard. Each owner gets a unique URL where all their property inspection reports are automatically collected.

## How Owners Register

### Method 1: Self-Registration on Landing Page

1. **Visit the Landing Page**
   - Go to: `http://localhost:8000`
   - Click the "Owner Portal" button in the top navigation

2. **Click "Register" Tab**
   - In the popup widget, click the "Register" tab

3. **Fill Registration Form**
   - **Full Name**: Enter your full name (e.g., "John Smith")
   - **Email**: Your email address for login
   - **Owner ID**: This is auto-generated from your name, or you can customize it
     - Examples: `john_smith`, `abc_properties`, `miami_rentals_001`
     - Only letters, numbers, underscores, and hyphens allowed
     - This becomes your unique dashboard URL
   - **Password**: Minimum 8 characters
   - **Confirm Password**: Re-enter your password

4. **Create Account**
   - Click "Create Owner Account"
   - You'll see a success message with your dashboard URL
   - Example: "Your dashboard URL: /owner/john_smith"

5. **Access Your Dashboard**
   - After registration, you'll be redirected to login
   - Use your email and password to sign in
   - You'll be taken directly to your personalized dashboard

## How Inspectors Link Reports to Owners

### In the Inspector Portal GUI (frontend.py):

1. **Enter Owner ID**
   - When submitting reports, enter the owner's ID in the "Owner ID" field
   - This links the report to that owner's dashboard

2. **Submit Reports**
   - Generate reports as usual
   - Reports are automatically sent to the owner's gallery

## Owner Dashboard Features

Once registered, owners can:

- **View All Properties**: See all properties linked to their account
- **Access Inspection Reports**: View detailed reports with photos
- **Download PDFs**: Get PDF versions of all reports
- **Photo Galleries**: Browse high-resolution inspection photos
- **Issue Tracking**: See critical, important, and minor issues
- **Historical Data**: Access past inspection reports

## Dashboard URL Structure

Each owner gets a unique URL:
```
http://localhost:8000/owner/{owner_id}
```

Examples:
- `http://localhost:8000/owner/john_smith`
- `http://localhost:8000/owner/abc_properties`
- `http://localhost:8000/owner/customer_12345`

## Security Features

- **Password Protected**: Each owner account is secured with a password
- **Unique Owner IDs**: No two owners can have the same ID
- **Private Galleries**: Owners only see their own properties
- **Secure Login**: JWT token-based authentication

## For Property Management Companies

If you manage multiple properties:
1. Create one account with a company ID (e.g., `abc_management`)
2. All properties managed by your company will appear in one dashboard
3. Inspectors will use your company ID when submitting reports

## Troubleshooting

### "Owner ID already taken"
- Choose a different ID
- Add numbers or your location (e.g., `john_smith_2`, `john_miami`)

### "Email already registered"
- Use the login option instead
- Or use a different email address

### Can't access dashboard after registration
1. Make sure you're logged in
2. Check the URL is correct: `/owner/your_id`
3. Try logging out and back in

### No properties showing in dashboard
- Confirm inspectors are using your correct Owner ID
- Check with your property manager that reports have been submitted
- Reports submitted before registration won't appear automatically

## Best Practices for Owner IDs

### Good Examples:
- `john_smith` - Personal name
- `abc_properties` - Company name
- `miami_rentals` - Location-based
- `customer_12345` - Numbered system

### Avoid:
- Spaces (use underscores instead)
- Special characters (except underscore and hyphen)
- Very long IDs (keep under 30 characters)
- Generic names like `owner` or `user`

## API Endpoints (Technical Details)

- **Registration**: `POST /api/portal/register-owner`
- **Login**: `POST /api/portal/login-owner`
- **Dashboard**: `GET /owner/{owner_id}`
- **API Dashboard Data**: `GET /api/portal/dashboard?portal_token={owner_id}`

## Next Steps After Registration

1. **Save Your Credentials**
   - Keep your Owner ID and password safe
   - Bookmark your dashboard URL

2. **Inform Your Property Manager**
   - Give them your Owner ID
   - They'll use it when submitting inspection reports

3. **Check Regularly**
   - New reports appear automatically
   - No email notifications yet (coming soon)

## Future Enhancements

- Email notifications for new reports
- Password reset functionality
- Multi-factor authentication
- Mobile app access
- Report comparison tools
- Maintenance scheduling integration