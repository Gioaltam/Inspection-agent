#!/bin/bash
# Production Deployment Script for Inspection Agent
# This script automates the deployment process

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
DEPLOY_DIR="/opt/inspection-agent"
BACKUP_DIR="/opt/backups/inspection-agent"
LOG_FILE="/var/log/inspection-agent-deploy.log"

# Functions
log() {
    echo -e "${GREEN}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $1" | tee -a "$LOG_FILE"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1" | tee -a "$LOG_FILE"
    exit 1
}

warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1" | tee -a "$LOG_FILE"
}

# Check if running as root
check_root() {
    if [[ $EUID -ne 0 ]]; then
        error "This script must be run as root"
    fi
}

# Check prerequisites
check_prerequisites() {
    log "Checking prerequisites..."
    
    # Check for Docker
    if ! command -v docker &> /dev/null; then
        error "Docker is not installed. Please install Docker first."
    fi
    
    # Check for Docker Compose
    if ! command -v docker-compose &> /dev/null; then
        error "Docker Compose is not installed. Please install Docker Compose first."
    fi
    
    # Check for Git
    if ! command -v git &> /dev/null; then
        error "Git is not installed. Please install Git first."
    fi
    
    log "All prerequisites are installed"
}

# Create necessary directories
create_directories() {
    log "Creating directories..."
    
    mkdir -p "$DEPLOY_DIR"
    mkdir -p "$BACKUP_DIR"
    mkdir -p "$DEPLOY_DIR/workspace/outputs"
    mkdir -p "$DEPLOY_DIR/workspace/incoming"
    mkdir -p "$DEPLOY_DIR/nginx/sites-enabled"
    mkdir -p "$DEPLOY_DIR/certbot/conf"
    mkdir -p "$DEPLOY_DIR/certbot/www"
    
    log "Directories created"
}

# Backup existing deployment
backup_existing() {
    if [ -d "$DEPLOY_DIR/.git" ]; then
        log "Backing up existing deployment..."
        
        BACKUP_NAME="backup_$(date +%Y%m%d_%H%M%S)"
        BACKUP_PATH="$BACKUP_DIR/$BACKUP_NAME"
        
        # Backup database
        if [ -f "$DEPLOY_DIR/workspace/inspection_portal.db" ]; then
            cp "$DEPLOY_DIR/workspace/inspection_portal.db" "$BACKUP_PATH.db"
            log "Database backed up to $BACKUP_PATH.db"
        fi
        
        # Backup .env file
        if [ -f "$DEPLOY_DIR/.env" ]; then
            cp "$DEPLOY_DIR/.env" "$BACKUP_PATH.env"
            log "Environment file backed up to $BACKUP_PATH.env"
        fi
        
        # Backup workspace
        if [ -d "$DEPLOY_DIR/workspace" ]; then
            tar -czf "$BACKUP_PATH.workspace.tar.gz" -C "$DEPLOY_DIR" workspace
            log "Workspace backed up to $BACKUP_PATH.workspace.tar.gz"
        fi
    fi
}

# Pull latest code
pull_latest_code() {
    log "Pulling latest code..."
    
    cd "$DEPLOY_DIR"
    
    if [ ! -d ".git" ]; then
        # Clone repository if not exists
        git clone https://github.com/yourusername/inspection-agent.git .
    else
        # Pull latest changes
        git pull origin main
    fi
    
    log "Code updated"
}

# Setup environment
setup_environment() {
    log "Setting up environment..."
    
    if [ ! -f "$DEPLOY_DIR/.env" ]; then
        if [ -f "$DEPLOY_DIR/.env.example" ]; then
            cp "$DEPLOY_DIR/.env.example" "$DEPLOY_DIR/.env"
            warning "Created .env from .env.example - Please update with your actual values!"
            
            # Generate secure keys
            SECRET_KEY=$(openssl rand -hex 32)
            JWT_SECRET=$(openssl rand -hex 32)
            
            # Update .env with generated keys
            sed -i "s/your_secret_key_here_use_secrets_token_hex_32/$SECRET_KEY/g" "$DEPLOY_DIR/.env"
            sed -i "s/your_jwt_secret_key_here/$JWT_SECRET/g" "$DEPLOY_DIR/.env"
            
            log "Generated secure keys"
            
            echo ""
            echo "================================================================"
            echo "IMPORTANT: Please edit $DEPLOY_DIR/.env and add:"
            echo "  - OPENAI_API_KEY"
            echo "  - AWS credentials (if using S3)"
            echo "  - Email settings (if using notifications)"
            echo "================================================================"
            echo ""
            
            read -p "Press Enter after updating .env file..."
        else
            error ".env.example not found"
        fi
    fi
    
    # Load environment variables
    source "$DEPLOY_DIR/.env"
}

# Build Docker images
build_images() {
    log "Building Docker images..."
    
    cd "$DEPLOY_DIR"
    docker-compose -f docker-compose.prod.yml build
    
    log "Docker images built"
}

# Start services
start_services() {
    log "Starting services..."
    
    cd "$DEPLOY_DIR"
    docker-compose -f docker-compose.prod.yml up -d
    
    # Wait for services to be healthy
    log "Waiting for services to be healthy..."
    sleep 10
    
    # Check service status
    docker-compose -f docker-compose.prod.yml ps
    
    log "Services started"
}

# Run database migrations
run_migrations() {
    log "Running database migrations..."
    
    cd "$DEPLOY_DIR"
    docker-compose -f docker-compose.prod.yml exec backend alembic upgrade head
    
    log "Migrations completed"
}

# Setup SSL certificates
setup_ssl() {
    log "Setting up SSL certificates..."
    
    read -p "Enter your domain name (e.g., inspection.yourdomain.com): " DOMAIN
    read -p "Enter your email for SSL notifications: " EMAIL
    
    if [ ! -z "$DOMAIN" ] && [ ! -z "$EMAIL" ]; then
        # Initial certificate request
        docker-compose -f docker-compose.prod.yml run --rm certbot certonly \
            --webroot \
            --webroot-path=/var/www/certbot \
            --email "$EMAIL" \
            --agree-tos \
            --no-eff-email \
            -d "$DOMAIN"
        
        log "SSL certificate obtained for $DOMAIN"
        
        # Update nginx configuration with domain
        sed -i "s/your_domain.com/$DOMAIN/g" "$DEPLOY_DIR/nginx/sites-enabled/inspection.conf"
        
        # Reload nginx
        docker-compose -f docker-compose.prod.yml exec nginx nginx -s reload
    else
        warning "Skipping SSL setup - running in HTTP only mode"
    fi
}

# Setup firewall
setup_firewall() {
    log "Setting up firewall..."
    
    if command -v ufw &> /dev/null; then
        ufw allow 22/tcp   # SSH
        ufw allow 80/tcp   # HTTP
        ufw allow 443/tcp  # HTTPS
        ufw --force enable
        
        log "Firewall configured"
    else
        warning "UFW not found, skipping firewall setup"
    fi
}

# Create systemd service
create_systemd_service() {
    log "Creating systemd service..."
    
    cat > /etc/systemd/system/inspection-agent.service << EOF
[Unit]
Description=Inspection Agent Application
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=$DEPLOY_DIR
ExecStart=/usr/local/bin/docker-compose -f docker-compose.prod.yml up -d
ExecStop=/usr/local/bin/docker-compose -f docker-compose.prod.yml down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
EOF
    
    systemctl daemon-reload
    systemctl enable inspection-agent
    
    log "Systemd service created and enabled"
}

# Health check
health_check() {
    log "Performing health check..."
    
    # Check backend API
    if curl -f http://localhost:8000/health > /dev/null 2>&1; then
        log "✓ Backend API is healthy"
    else
        error "Backend API health check failed"
    fi
    
    # Check gallery
    if curl -f http://localhost:8005 > /dev/null 2>&1; then
        log "✓ Gallery server is healthy"
    else
        warning "Gallery server health check failed"
    fi
    
    log "Health check completed"
}

# Print summary
print_summary() {
    echo ""
    echo "================================================================"
    echo "                    DEPLOYMENT COMPLETE!"
    echo "================================================================"
    echo ""
    echo "Services are running at:"
    echo "  - Backend API: http://localhost:8000"
    echo "  - Gallery: http://localhost:8005"
    echo ""
    echo "Next steps:"
    echo "  1. Update .env file with production values if not done"
    echo "  2. Configure your domain DNS to point to this server"
    echo "  3. Run: docker-compose -f docker-compose.prod.yml logs -f"
    echo "     to monitor logs"
    echo ""
    echo "Useful commands:"
    echo "  - Start services: systemctl start inspection-agent"
    echo "  - Stop services: systemctl stop inspection-agent"
    echo "  - View logs: docker-compose -f docker-compose.prod.yml logs"
    echo "  - Restart services: docker-compose -f docker-compose.prod.yml restart"
    echo ""
    echo "================================================================"
}

# Main deployment flow
main() {
    log "Starting Inspection Agent deployment..."
    
    check_root
    check_prerequisites
    create_directories
    backup_existing
    pull_latest_code
    setup_environment
    build_images
    start_services
    run_migrations
    setup_ssl
    setup_firewall
    create_systemd_service
    health_check
    print_summary
    
    log "Deployment completed successfully!"
}

# Run main function
main "$@"