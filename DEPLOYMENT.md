# Inspection Agent - Deployment Guide

## Overview
This guide covers the complete deployment process for the Inspection Agent application, including both the employee desktop app and the web-based client gallery.

## Architecture
```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Employee App   │────▶│   Backend API   │────▶│    Database     │
│  (Desktop GUI)  │     │   (FastAPI)     │     │  (PostgreSQL)   │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                               │
                               ▼
                        ┌─────────────────┐     ┌─────────────────┐
                        │  Client Gallery │────▶│   S3 Storage    │
                        │   (Web Portal)  │     │   (Optional)    │
                        └─────────────────┘     └─────────────────┘
```

## Prerequisites

### System Requirements
- Ubuntu 20.04+ or similar Linux distribution
- 4GB RAM minimum (8GB recommended)
- 20GB storage minimum
- Domain name (for production)
- SSL certificate (Let's Encrypt recommended)

### Software Requirements
- Docker 20.10+
- Docker Compose 2.0+
- Git
- Python 3.11+ (for local development)

## Quick Start (Development)

1. **Clone the repository:**
```bash
git clone https://github.com/yourusername/inspection-agent.git
cd inspection-agent
```

2. **Copy and configure environment variables:**
```bash
cp .env.example .env
# Edit .env with your configuration
nano .env
```

3. **Required environment variables:**
```env
# Critical - Must be set
OPENAI_API_KEY=your_openai_key_here
SECRET_KEY=generate_with_openssl_rand_hex_32
JWT_SECRET_KEY=generate_with_openssl_rand_hex_32

# Database (for production)
DATABASE_URL=postgresql://user:pass@localhost/dbname

# Optional - S3 Storage
AWS_ACCESS_KEY_ID=your_aws_key
AWS_SECRET_ACCESS_KEY=your_aws_secret
S3_BUCKET_NAME=your_bucket_name
```

4. **Start development servers:**
```bash
# Backend API
python -m uvicorn backend.app.main:app --reload --port 8000

# Gallery Server
python simple_portal_server.py

# Employee GUI
python frontend_enhanced.py
```

## Production Deployment

### Method 1: Automated Deployment Script

1. **Run the deployment script as root:**
```bash
sudo chmod +x deploy.sh
sudo ./deploy.sh
```

This script will:
- Check prerequisites
- Set up directories
- Configure environment
- Build Docker images
- Start all services
- Set up SSL certificates
- Configure firewall
- Create systemd service

### Method 2: Manual Docker Deployment

1. **Prepare the server:**
```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Install Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose
```

2. **Clone and configure:**
```bash
cd /opt
sudo git clone https://github.com/yourusername/inspection-agent.git
cd inspection-agent
sudo cp .env.example .env
sudo nano .env  # Configure your settings
```

3. **Build and start services:**
```bash
sudo docker-compose -f docker-compose.prod.yml build
sudo docker-compose -f docker-compose.prod.yml up -d
```

4. **Set up SSL (optional but recommended):**
```bash
# Get SSL certificate
sudo docker-compose -f docker-compose.prod.yml run --rm certbot certonly \
    --webroot \
    --webroot-path=/var/www/certbot \
    --email your-email@domain.com \
    --agree-tos \
    --no-eff-email \
    -d your-domain.com

# Update nginx configuration
sudo sed -i 's/your_domain.com/your-actual-domain.com/g' nginx/sites-enabled/inspection.conf

# Restart nginx
sudo docker-compose -f docker-compose.prod.yml restart nginx
```

### Method 3: Cloud Deployment (AWS/DigitalOcean)

#### AWS EC2 Deployment

1. **Launch EC2 instance:**
   - AMI: Ubuntu 20.04 LTS
   - Instance type: t3.medium or larger
   - Security groups: Allow ports 22, 80, 443

2. **Connect and deploy:**
```bash
ssh -i your-key.pem ubuntu@your-ec2-ip
# Follow Manual Docker Deployment steps above
```

#### DigitalOcean Droplet

1. **Create Droplet:**
   - Image: Ubuntu 20.04 LTS
   - Size: 2GB RAM minimum
   - Enable backups

2. **Deploy using SSH:**
```bash
ssh root@your-droplet-ip
# Follow Manual Docker Deployment steps above
```

## Employee Desktop App Distribution

### Windows
1. **Build executable:**
```bash
pip install pyinstaller
pyinstaller --onefile --windowed frontend_enhanced.py
```

2. **Distribute to employees:**
   - Share the `dist/frontend_enhanced.exe` file
   - Provide `.env` file with API endpoint configured

### macOS
```bash
pyinstaller --onefile --windowed --osx-bundle-identifier com.yourcompany.inspection frontend_enhanced.py
```

### Linux
```bash
pyinstaller --onefile frontend_enhanced.py
```

## Configuration Management

### Environment Variables
All configuration is managed through environment variables. Key settings:

- `ENVIRONMENT`: Set to "production" for production deployment
- `DEBUG`: Set to "false" in production
- `BACKEND_API_URL`: URL where backend API is hosted
- `CORS_ORIGINS`: Allowed origins for CORS

### Database Migrations
```bash
# Run migrations
docker-compose -f docker-compose.prod.yml exec backend alembic upgrade head

# Create new migration
docker-compose -f docker-compose.prod.yml exec backend alembic revision --autogenerate -m "description"
```

## Monitoring & Maintenance

### View Logs
```bash
# All services
docker-compose -f docker-compose.prod.yml logs -f

# Specific service
docker-compose -f docker-compose.prod.yml logs -f backend
```

### Backup Database
```bash
# PostgreSQL backup
docker-compose -f docker-compose.prod.yml exec db pg_dump -U inspection_user inspection_portal > backup.sql

# SQLite backup (if using SQLite)
cp workspace/inspection_portal.db backup_$(date +%Y%m%d).db
```

### Update Application
```bash
cd /opt/inspection-agent
git pull origin main
docker-compose -f docker-compose.prod.yml build
docker-compose -f docker-compose.prod.yml down
docker-compose -f docker-compose.prod.yml up -d
```

### Health Checks
```bash
# Check API health
curl http://localhost:8000/health

# Check service status
docker-compose -f docker-compose.prod.yml ps
```

## Security Considerations

1. **Always use HTTPS in production**
2. **Change default passwords and keys**
3. **Keep Docker and dependencies updated**
4. **Enable firewall (ufw)**
5. **Regular backups**
6. **Monitor logs for suspicious activity**
7. **Use environment-specific configurations**

## Troubleshooting

### Common Issues

1. **Port already in use:**
```bash
# Find process using port
sudo lsof -i :8000
# Kill process
sudo kill -9 <PID>
```

2. **Docker permission denied:**
```bash
sudo usermod -aG docker $USER
# Log out and back in
```

3. **Database connection failed:**
- Check DATABASE_URL in .env
- Ensure database service is running
- Check firewall rules

4. **SSL certificate issues:**
```bash
# Renew certificate
docker-compose -f docker-compose.prod.yml run --rm certbot renew
```

## Support

For issues or questions:
1. Check logs: `docker-compose logs`
2. Review this documentation
3. Check GitHub issues
4. Contact support team

## License
[Your License Here]