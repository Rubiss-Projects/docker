---
applyTo: "{actual/**,actual-ai/**}"
---

# Actual Budget Expert Instructions

You are an expert in Actual Budget configuration for personal finance management and budget tracking.

## Service Overview
Actual Budget is a local-first personal finance tool based on zero-based budgeting principles. It provides envelope-style budgeting, bank synchronization, mobile apps, and complete local data control. Actual-AI may provide AI-powered financial insights (if configured).

## Technical Configuration

### Docker Compose Patterns

**Actual (Main App)**:
```yaml
ports:
  - "5006:5006"
environment:
  - TZ=America/Chicago
volumes:
  - ./data:/data
restart: unless-stopped
```

**Actual-AI (Optional AI Features)**:
```yaml
ports:
  - "5007:5007"
environment:
  - TZ=America/Chicago
  - ACTUAL_SERVER_URL=http://actual:5006
  - OPENAI_API_KEY=${OPENAI_API_KEY}  # Optional for AI features
volumes:
  - ./data:/data
restart: unless-stopped
```

### Critical Files
- `data/server-files/` - Budget data
- `data/user-files/` - User preferences

### Default Ports
- 5006 - Actual Budget web UI
- 5007 - Actual-AI (if enabled)

## Common Tasks

### First-Time Setup
1. Access UI: `http://localhost:5006`
2. Create or import budget file
3. Set up budget categories
4. Add accounts (checking, savings, credit cards)
5. Configure bank sync (optional, requires SimpleFIN)

### Create Budget
1. File > New Budget
2. Enter budget name
3. Start month: Current month
4. Create

### Add Accounts
Accounts > Add Account:
1. **Account Type**: Checking, Savings, Credit Card, etc.
2. **Account Name**: Wells Fargo Checking
3. **Starting Balance**: Current balance
4. **Save**

### Create Budget Categories
Budget view:
1. Category Groups: Income, Bills, Everyday, Savings
2. Add categories within groups
3. Set monthly budget amounts

### Import Transactions
Accounts > [Account] > Import:
1. Upload CSV/OFX file from bank
2. Map columns (Date, Payee, Amount)
3. Review and import
4. Categorize transactions

### Bank Sync (SimpleFIN)
Settings > Bank Sync:
1. Sign up for SimpleFIN (third-party service)
2. Enter SimpleFIN setup token
3. Connect bank accounts
4. Automatic transaction downloads

### Reconcile Account
Accounts > [Account] > Reconcile:
1. Enter current account balance from bank
2. Review uncleared transactions
3. Mark transactions as cleared
4. Reconcile difference

### Mobile Access
**Mobile Apps**:
- iOS: Actual Budget (App Store)
- Android: Actual Budget (Play Store)

Server URL: `http://your-server-ip:5006` or `https://budget.benlawson.dev`

### Budget Reports
Reports view:
- Net Worth over time
- Spending by category
- Income vs. Expenses
- Cash flow

### Export Data
File > Export:
- Format: CSV or JSON
- All transactions and budget data
- For backup or external analysis

## Integration Points

### Homepage Dashboard
```yaml
- Actual Budget:
    icon: actual.png
    href: http://localhost:5006
    description: Personal finance and budgeting
```

### Nginx Proxy Manager
```
Domain: budget.benlawson.dev
Forward: http://actual:5006
Websockets: Yes
SSL: Let's Encrypt
```

### SimpleFIN (Bank Sync)
Third-party service for automatic bank connections:
- Cost: ~$2/month per bank
- Supports most US banks
- Automatic transaction downloads

### Actual-AI Integration
If running actual-ai:
- AI-powered categorization suggestions
- Spending insights and trends
- Budget optimization recommendations

## Troubleshooting

### Cannot Access UI
1. Check container: `docker ps`
2. Test port: `curl http://localhost:5006`
3. Review logs: `docker logs actual`
4. Verify port 5006 not in use

### Budget File Won't Open
1. Check file not corrupted
2. Verify data directory permissions
3. Try creating new budget
4. Restore from backup if needed

### Bank Sync Not Working
1. Verify SimpleFIN token is correct
2. Check internet connectivity
3. Re-authenticate with bank
4. Review SimpleFIN service status

### Transactions Not Importing
1. Check CSV format matches expected columns
2. Verify date format (YYYY-MM-DD)
3. Ensure amount is numeric
4. Review import mapping

### Mobile App Won't Connect
1. Verify server URL is accessible
2. Check HTTPS certificate valid (if using SSL)
3. Test in browser first
4. Verify firewall allows connection

## Best Practices

1. **Regular Reconciliation**: Weekly account reconciliation
2. **Zero-Based Budget**: Assign every dollar a job
3. **Emergency Fund**: Build 3-6 months expenses category
4. **Debt Payoff**: Use targeted categories for debt
5. **Regular Backups**: Backup budget file weekly
6. **Envelope Method**: Allocate money to categories at month start
7. **Review Monthly**: Adjust budget based on actual spending

## Security Considerations

- **No Built-in Auth**: Actual has no password protection
- **Reverse Proxy**: Use auth via Nginx Proxy Manager
- **HTTPS**: SSL for remote access
- **Port Exposure**: Don't expose 5006 publicly without auth
- **Bank Data**: Sensitive financial information
- **SimpleFIN Token**: Protect token (bank access)

## Advanced Configuration

### Multi-Device Sync
Actual uses local-first sync:
1. Each device has full data copy
2. Syncs changes when connected
3. Conflict resolution automatic
4. Works offline, syncs when online

### Budget Templates
Create template budgets:
1. Set up ideal budget structure
2. File > Duplicate
3. Use as starting point for new months

### Scheduled Transactions
Automate recurring transactions:
1. Accounts > [Account] > Scheduled Transactions
2. Add schedule (monthly bills, paychecks)
3. Auto-post or review before posting

### Custom Rules
Automate transaction categorization:
1. Settings > Rules
2. Create rule: If payee contains "Amazon" → Category "Shopping"
3. Auto-categorize future transactions

### Budget Goals
Set savings goals:
1. Category > Edit > Goal
2. Types: Monthly savings, target amount by date
3. Track progress automatically

### Split Transactions
For mixed-category transactions:
1. Transaction > Split
2. Allocate amounts to multiple categories
3. Save split

## Budgeting Principles

### Zero-Based Budgeting
- Assign every dollar before month starts
- Income - Budgeted = $0
- No money left "unassigned"

### Envelope Method
- Each category is an "envelope"
- Put money in at month start
- Spend from envelopes during month
- Stop when envelope empty

### Four Rules (YNAB-inspired)
1. **Give Every Dollar a Job**: Assign all income
2. **Embrace Your True Expenses**: Budget for irregular expenses
3. **Roll With The Punches**: Adjust budget as needed
4. **Age Your Money**: Spend last month's income

## Backup and Restore

### Backup Budget
```powershell
docker compose stop
tar -czf "actual-backup-$(Get-Date -Format 'yyyyMMdd').tar.gz" data/
docker compose start
```

Or use Actual's built-in export:
- File > Export
- Save .zip file

### Restore Budget
```powershell
docker compose stop
tar -xzf actual-backup-YYYYMMDD.tar.gz
docker compose start
```

Or use Actual's import:
- File > Import
- Select .zip file

### Cloud Backup
Sync data directory to cloud storage:
```yaml
volumes:
  - /path/to/synced-folder:/data
```

Use Dropbox, Google Drive, etc. sync client.

## API Usage (Advanced)

Actual has an API for automation:

### Get Budget Data
```javascript
const actual = require('@actual-app/api');

await actual.init({
  serverURL: 'http://localhost:5006',
  password: '',
  dataDir: './data',
});

await actual.downloadBudget('budget-id');
const accounts = await actual.getAccounts();
console.log(accounts);

await actual.shutdown();
```

### Add Transaction
```javascript
await actual.addTransactions('account-id', [{
  date: '2025-01-15',
  amount: -5023,  // Cents
  payee_name: 'Coffee Shop',
  notes: 'Morning coffee',
}]);
```

### Automation Examples
- Import transactions from CSV via script
- Auto-categorize based on custom logic
- Generate reports and send via email
- Sync with external systems

## Reporting

### Net Worth Report
Tracks total assets - liabilities over time:
- View trends
- Set goals
- Export data

### Spending Report
Breakdown by category:
- Monthly comparison
- Category trends
- Budget vs. actual

### Cash Flow Report
Income vs. expenses:
- Monthly cash flow
- Income trends
- Expense trends

## Mobile App Features

- Full budget access
- Add/edit transactions on-the-go
- Account reconciliation
- Budget adjustments
- Offline mode (syncs when online)
- Camera receipt capture (manual entry)

## Comparison with Other Tools

**vs. YNAB (You Need A Budget)**:
- Actual: Self-hosted, one-time cost, local data
- YNAB: Cloud-only, $99/year subscription

**vs. Mint**:
- Actual: Privacy-focused, no ads, manual/sync imports
- Mint: Free, ad-supported, automatic sync

**vs. Spreadsheets**:
- Actual: Purpose-built, mobile apps, bank sync
- Spreadsheets: Flexible, manual, no mobile sync

## SimpleFIN Setup

1. Sign up: https://simplefin.org/
2. Subscribe to bank sync ($2/mo per bank)
3. Connect bank accounts through SimpleFIN
4. Copy setup token
5. Actual > Settings > Bank Sync > Enter token
6. Select accounts to sync
7. Transactions download automatically

## Common Budget Categories

**Income**:
- Salary
- Freelance
- Interest/Dividends

**Fixed Expenses**:
- Rent/Mortgage
- Insurance
- Loan Payments

**Variable Expenses**:
- Groceries
- Dining Out
- Gas
- Entertainment

**Savings**:
- Emergency Fund
- Retirement
- Vacation

**Debt**:
- Credit Card Payments
- Student Loans
- Car Loan

This self-hosted personal finance tool provides powerful zero-based budgeting with local data control, bank synchronization, and mobile access for comprehensive financial management in the Docker homelab.
