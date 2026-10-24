# Deploying the demo to AWS (one EC2 server)

The public demo runs the same Docker Compose stack as your PC on one small EC2 server. Only the website is
reachable from the internet, and it uses **demo data only**: Swiggy sign-in is switched off and no real order can
be placed. Your real Swiggy account never touches this server.

```
Internet --(port 80)--> EC2 server
                          frontend (Next.js) --> backend (FastAPI + LangGraph) --> mock Swiggy MCP
                                                    |--> Redis (sessions)   |--> Postgres
                        (only port 80 is open to everyone; SSH only from your own IP)
```

## 0. Before anything: a budget alert
AWS console, search **Budgets**, then **Create budget**, then **Zero spend budget** (or a $5 monthly budget) with
your email. You get an email the moment anything starts costing money.

## 1. Launch the server (about 5 minutes)
AWS console, top-right region **Asia Pacific (Mumbai) ap-south-1**, then search **EC2**, then **Launch instance**:

| Setting | Value |
|---|---|
| Name | `sarah-demo` |
| Image (AMI) | **Ubuntu Server 24.04 LTS** |
| Instance type | **t3.small** (2 GB RAM; t3.micro's 1 GB is too small for five containers) |
| Key pair | **Create new key pair**, name `sarah-demo`, type RSA, `.pem`; keep the file safe (only needed for SSH from your PC) |
| Network settings | Tick **Allow SSH traffic from: My IP** and **Allow HTTP traffic from the internet**. Leave HTTPS unticked for now |
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
password, and builds and starts everything. It ends with `Done. Open http://<ip>`.

If **EC2 Instance Connect** fails, the SSH rule only allows your IP: edit the instance's security group and add
the inbound SSH rule for the EC2 Instance Connect service of your region, or connect from your PC with
`ssh -i sarah-demo.pem ubuntu@<public-ip>`.

## 3. Check it
- Open `http://<public-ip>` in your browser: Sarah with the "Demo mode" banner.
- On the server: `cd ~/swiggy-ai-assistant && sudo docker compose ps` shows all five services running.
- Only the website is public: `http://<public-ip>:8000` must **not** load.

## Updating after you push new code
Connect again and run the same `curl ... | bash` line. It pulls the latest code and rebuilds.

## Costs and turning it off
- The server and its public IP cost money by the hour. New AWS accounts get free-plan credits; check
  **Billing and Cost Management** for your remaining credits now and then.
- **Stop** the instance when you don't need the demo (no server charge while stopped; the disk still costs a
  little). **Terminate** it when you are done for good, and delete the key pair and security group.
- A stopped and started instance gets a **new public IP** unless you attach an Elastic IP (which is charged
  while the instance is stopped).

## Not done yet (next steps)
- HTTPS with a domain name (Caddy or an AWS load balancer with a certificate).
- Deploy from GitHub Actions instead of by hand (build images, push to Amazon ECR, pull on the server).
- Rate limiting on `/api/chat` before sharing the link widely; the demo has no user accounts.
