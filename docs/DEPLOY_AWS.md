# Deploying the demo to AWS (one EC2 server)

The public demo runs the same Docker Compose stack as your PC on one small EC2 server. Only the website is
reachable from the internet, and it uses **demo data only**: Swiggy sign-in is switched off and no real order can
be placed. Your real Swiggy account never touches this server.

```
Internet --(https, 443)--> EC2 server
                            Caddy (free Let's Encrypt certificate) --> frontend (Next.js)
                              --> backend (FastAPI + LangGraph) --> mock Swiggy MCP, Redis, Postgres
                          (only Caddy's ports 80 and 443 are published; everything else is private)
```

## 0. Before anything: a budget alert
AWS console, search **Budgets**, then **Create budget**, then **Zero spend budget** (or a $5 monthly budget) with
your email. You get an email the moment anything starts costing money.

## 1. Launch the server (about 5 minutes)
AWS console (new accounts get a region from their address; this demo runs in Sydney, `ap-southeast-2`), search
**EC2**, then **Launch instance** (choose **Launch without a walkthrough** if asked):

| Setting | Value |
|---|---|
| Name | `sarah-demo` |
| Image (AMI) | **Ubuntu Server 24.04 LTS** |
| Instance type | **t3.small** (2 GB RAM; t3.micro's 1 GB is too small for six containers; t3.small was free-plan eligible) |
| Key pair | **Create new key pair**, name `sarah-demo`, type RSA, `.pem`; keep the file safe (only needed for SSH from your PC) |
| Network settings | Tick **Allow SSH traffic**, **Allow HTTPS traffic from the internet** and **Allow HTTP traffic from the internet** (HTTP is needed for the certificate check and redirects to HTTPS). SSH: "Anywhere" keeps the browser-based EC2 Instance Connect working; login still needs the key |
| Storage | **20 GiB gp3** |

Click **Launch instance**, then open the instance and wait until **Instance state: Running** and
**Status checks: 2/2 passed**.

## 2. Install and start the app (about 10 minutes, mostly waiting)
On the instance page click **Connect**, then the **EC2 Instance Connect** tab, then **Connect**. A terminal opens in
your browser. Paste:

```
curl -fsSL https://raw.githubusercontent.com/Sasanksurya/swiggy-ai-assistant/main/deploy/setup-ec2.sh | bash
```

It installs Docker, adds 2 GB of swap, downloads the code, creates a private `.env` with a random database
password and an HTTPS name for the server (`<ip-with-dashes>.sslip.io`, a free service that points that name at
your IP), and builds and starts everything. It ends with `Done. Open https://<ip-with-dashes>.sslip.io`.
The first visit can take up to a minute while Caddy gets the certificate.

If **EC2 Instance Connect** fails, check that the security group allows SSH from Anywhere (Instance Connect comes
from AWS's addresses, not yours), or connect from your PC with `ssh -i sarah-demo.pem ubuntu@<public-ip>`.

## 3. Check it
- Open `https://<ip-with-dashes>.sslip.io`: Sarah with the "Demo mode" banner and a padlock. Voice input works
  only on HTTPS (browsers block the microphone on plain http).
- On the server: `cd ~/swiggy-ai-assistant && sudo docker compose ps` shows six services running.
- Only Caddy is public: `http://<public-ip>:8000` and `:3000` must **not** load.

## Adding HTTPS to a server launched without it
EC2, then **Instances**, select the instance, **Security** tab, click the security group, **Edit inbound rules**,
**Add rule**: type **HTTPS**, source **Anywhere-IPv4**, then **Save rules**. Then run the setup line again.

## Updating after you push new code
Connect again and run the same `curl ... | bash` line. It pulls the latest code and rebuilds.

## Costs and turning it off
- The server and its public IP cost money by the hour. New AWS accounts get free-plan credits; check
  **Billing and Cost Management** for your remaining credits now and then.
- **Stop** the instance when you don't need the demo (no server charge while stopped; the disk still costs a
  little). **Terminate** it when you are done for good, and delete the key pair and security group.
- A stopped and started instance gets a **new public IP** unless you attach an Elastic IP (which is charged
  while the instance is stopped). After a restart, run the setup line again: it picks up the new IP, and the
  site moves to the matching `sslip.io` name.

## Not done yet (next steps)
- A real domain name instead of `sslip.io` (change `SITE_ADDRESS` in `.env`).
- Deploy from GitHub Actions instead of by hand (build images, push to Amazon ECR, pull on the server).
- Rate limiting on `/api/chat` before sharing the link widely; the demo has no user accounts.
