# AWS Sage: Your AI Assistant's Gateway to the Cloud

**Making cloud infrastructure management as simple as having a conversation**

*By Arun Sanna | December 2025*

> **Open Source**: [github.com/arunsanna/aws-sage](https://github.com/arunsanna/aws-sage)

---

## The Challenge: Cloud Complexity

Imagine you're managing a company's cloud infrastructure on Amazon Web Services (AWS). You have hundreds of servers, databases, storage buckets, and security configurations spread across multiple regions. Finding what you need feels like searching for a needle in a haystack.

Today, engineers spend hours clicking through dashboards, running commands, and piecing together information from different screens. When something breaks at 2 AM, the investigation process is slow and stressful.

**What if you could simply ask your AI assistant: "What's wrong with my payment system?"**

That's exactly what AWS Sage makes possible.

---

## What is AWS Sage?

AWS Sage is a bridge between AI assistants (like Claude) and Amazon Web Services. It lets you manage your cloud infrastructure through natural conversation instead of complex commands.

![MCP Ecosystem Statistics 2025](../images/mcp-ecosystem-stats.png)
*The Model Context Protocol ecosystem has grown rapidly, with thousands of integrations connecting AI assistants to real-world tools and services.*

Instead of navigating through dozens of screens and memorizing technical commands, you can simply ask questions like:

- *"Show me all our production servers"*
- *"What resources are we paying for but not using?"*
- *"What happens if I delete this security setting?"*

AWS Sage understands your question, gathers information from across your entire AWS account, and presents a clear answer.

---

## The Problem with Existing Solutions

Amazon offers official tools for connecting AI assistants to AWS, but they come with a significant limitation: **fragmentation**.

![Architecture Comparison](../images/architecture-comparison.png)
*Left: The traditional approach requires 15 separate connections, one for each AWS service. Right: AWS Sage provides a single, unified connection with built-in intelligence.*

Think of it like having 15 different phone numbers to reach different departments at the same company. Want to know about your storage? Call one number. Servers? A different number. Security? Yet another number.

This fragmentation creates real problems:

- **You can't see the big picture.** Each tool only knows about its own area.
- **Finding related information is tedious.** You have to manually piece together answers from multiple sources.
- **Nobody understands connections.** The storage tool doesn't know which servers use that storage.

AWS Sage solves this by providing **one unified connection** that understands your entire infrastructure as a connected system.

---

## What Makes AWS Sage Different

### See Everything at Once

With AWS Sage, finding resources across your entire cloud is effortless.

**Traditional approach:**
1. Open the server dashboard, search for "production" tag
2. Open the database dashboard, search for "production" tag
3. Open the storage dashboard, search for "production" tag
4. Manually compile results into a spreadsheet

**With AWS Sage:**
> *"Find all resources tagged production"*

One question. Complete answer. Every server, database, storage bucket, and security configuration—all in a single response.

---

### Understand How Things Connect

Modern cloud infrastructure is interconnected. A single application might depend on servers, databases, encryption keys, security rules, and secret credentials. Understanding these connections is crucial for safe operations.

![Tool Categories](../images/tool-categories.png)
*AWS Sage provides 30 intelligent tools organized across 10 categories, from basic queries to advanced analysis.*

When you ask AWS Sage about a resource, it doesn't just tell you that resource exists—it tells you what it connects to:

> *"What does our payment processor depend on?"*

**Response:** "Your payment processor uses:
- A private network connection in the Virginia region
- A security rule allowing traffic on port 443
- A database role with read access to customer data
- An encryption key for securing transactions
- API credentials stored in Secrets Manager"

This information, which previously required 30 minutes of manual investigation, arrives in seconds.

---

### Know What Breaks Before You Break It

One of the most dangerous operations in cloud management is deleting resources. Delete the wrong thing, and your entire application might go offline.

AWS Sage provides **impact analysis**—it tells you exactly what will be affected before you make changes.

> *"What happens if I delete this security rule?"*

**Response:** "⚠️ Warning: This security rule is currently used by:
- 3 web servers handling customer traffic
- 2 background processors for order fulfillment
- 1 database containing customer records

Deleting this rule will immediately block all network traffic to these resources, causing a complete service outage."

Now you can make informed decisions instead of hoping nothing breaks.

---

### Automatic Problem Investigation

When something goes wrong in production, time is critical. Every minute of downtime costs money and damages customer trust.

![Incident Investigation Workflow](../images/incident-workflow.png)
*When you report a problem, AWS Sage automatically investigates multiple potential causes and presents consolidated findings.*

Traditional troubleshooting requires checking logs, reviewing metrics, examining configurations, and tracing connections—a process that can take 30 minutes or more.

With AWS Sage:

> *"Investigate why our checkout system is failing"*

**Response:** "Investigation complete. I found the following issues:

1. **Memory exhaustion** - The system ran out of memory 47 times in the last hour
2. **Timeout configuration** - Current 3-second timeout is too short for payment processing
3. **Downstream dependency** - The inventory database is responding slowly (2.3 second average)

Recommendation: Increase memory allocation from 512MB to 1024MB and extend timeout to 10 seconds."

What took 30 minutes now takes 30 seconds.

---

### Find Hidden Costs

Cloud bills can be surprising. Resources get created for testing and forgotten. Servers run 24/7 when they're only needed during business hours. Storage accumulates without cleanup.

AWS Sage helps you find money you're wasting:

> *"Find resources we're paying for but not using"*

**Response:** "I found $847/month in potential savings:

| Resource | Issue | Monthly Cost |
|----------|-------|--------------|
| 3 servers | Stopped for 30+ days | $312 |
| 12 storage volumes | Not attached to anything | $245 |
| 5 IP addresses | Allocated but unused | $18 |
| 2 databases | Zero connections this month | $272 |

Would you like details on any of these?"

---

## Built-In Safety

Working with production infrastructure requires caution. A single mistake can cause outages affecting thousands of users. AWS Sage includes multiple layers of protection.

![Safety System](../images/safety-system.png)
*AWS Sage's three-tier safety system ensures you can explore freely while protecting against accidental damage.*

### Three Safety Modes

**Exploration Mode (Default)**
Perfect for investigation and learning. You can ask any question and view any resource, but you cannot make changes. This is ideal for:
- New team members learning the infrastructure
- Investigating issues without risk
- Generating reports and audits

**Standard Mode**
For day-to-day operations. You can make changes, but AWS Sage will ask for confirmation before doing anything potentially risky:

> "You're about to restart 3 production servers. This will cause approximately 30 seconds of downtime. Proceed? (yes/no)"

**Full Access Mode**
For automated systems and experienced operators. Still includes guardrails for the most dangerous operations.

### Operations That Are Always Blocked

Some operations are so dangerous that AWS Sage will never perform them, regardless of mode:

- Deleting audit logs (removes evidence of what happened)
- Disabling security monitoring (removes threat detection)
- Removing encryption keys (makes data permanently inaccessible)
- Leaving your organization (removes all access controls)

These protections ensure that even a compromised or confused system cannot cause catastrophic damage.

---

## Safe Development with LocalStack

Professional development requires testing changes before applying them to production. AWS Sage integrates with LocalStack—a tool that simulates AWS on your own computer.

This means you can:

> *"Switch to my local test environment"*
> *"Create a test database"*
> *"Try deleting this security rule"*

All without touching your real infrastructure. When you're confident everything works:

> *"Compare my test environment with production"*

AWS Sage shows exactly what's different, helping you catch mistakes before they reach customers.

---

## Managing Multiple Accounts

Large organizations often use separate AWS accounts for different purposes: development, testing, staging, production, security, and logging. Switching between them traditionally requires logging out, logging in, and reconfiguring tools.

With AWS Sage:

> *"Switch to the production account"*

You're immediately working with production resources. AWS Sage clearly shows which account you're in and warns you when performing sensitive operations:

> "⚠️ You are now operating in PRODUCTION (Account: 123456789). Operations will affect live customer data."

---

## Real-World Example

Let's walk through a realistic scenario: your e-commerce checkout is slow, and customers are abandoning their carts.

**Step 1: Investigate the problem**
> *"Investigate slow checkout performance"*

AWS Sage checks your servers, databases, and network. It finds that your payment processing server is running at 95% memory usage.

**Step 2: Understand the impact**
> *"What services depend on the payment processor?"*

You learn it handles all credit card transactions, PayPal payments, and gift card redemptions.

**Step 3: Find a solution**
> *"What would it cost to double the payment processor's capacity?"*

AWS Sage estimates an additional $156/month.

**Step 4: Make the change safely**
> *"Increase payment processor memory to 2048MB"*

AWS Sage asks for confirmation, applies the change, and monitors the result.

**Step 5: Verify the fix**
> *"How is checkout performance now?"*

Response times dropped from 4.2 seconds to 0.8 seconds. Problem solved.

Total time: 5 minutes. Traditional approach: 2+ hours.

---

## Getting Started

AWS Sage works with Claude (Anthropic's AI assistant) through the Model Context Protocol. Setup takes about 10 minutes:

1. **Install AWS Sage** on your computer
2. **Configure Claude Desktop** to use AWS Sage
3. **Connect your AWS credentials** (the same ones you already use)
4. **Start asking questions**

Detailed instructions are available at [github.com/arunsanna/aws-sage](https://github.com/arunsanna/aws-sage).

---

## Who Benefits Most

**DevOps Engineers** spend less time on routine investigation and more time on valuable improvements.

**Developers** can understand infrastructure without becoming infrastructure experts.

**Managers** get quick answers about costs, resources, and system health without waiting for reports.

**Security Teams** can investigate alerts faster and understand the blast radius of potential issues.

**New Team Members** can explore and learn without fear of breaking anything.

---

## The Bigger Picture

Cloud infrastructure is becoming increasingly complex. The old approach—memorizing commands, clicking through dashboards, manually correlating information—doesn't scale.

AI assistants are changing how we interact with software. AWS Sage extends this transformation to cloud infrastructure, making it accessible through natural conversation.

The goal isn't to replace infrastructure expertise. It's to amplify it. Experienced engineers move faster. New team members contribute sooner. Everyone makes better-informed decisions.

**The future of cloud management isn't about learning more commands. It's about asking better questions.**

---

## Learn More

- **Repository**: [github.com/arunsanna/aws-sage](https://github.com/arunsanna/aws-sage)
- **License**: MIT (free for any use)
- **Author**: Arun Sanna (arun.sanna@outlook.com)

AWS Sage is open source. Contributions, feedback, and questions are welcome.

---

*AWS Sage v1.0.0 | December 2025*
