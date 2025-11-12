# ClickUp Data Exporter

A robust Django-based service for exporting and caching ClickUp workspace data with automated background processing.

## Overview

The ClickUp Data Exporter is designed to efficiently extract comprehensive data from ClickUp workspaces, including:
- Tasks with detailed metadata and status information
- Time tracking entries and summaries
- Workspace structure (spaces, lists, folders)
- Time-in-status analytics

The service uses asynchronous processing for optimal performance and implements intelligent caching to minimize API calls while providing fresh data through scheduled exports.

## Features

- **Automated Data Export**: Scheduled Celery tasks fetch ClickUp data every 5 hours
- **Comprehensive Data Coverage**: Exports tasks, time entries, and workspace structure
- **Intelligent Caching**: Redis-based caching with version control and TTL management
- **Rate Limiting Handling**: Built-in retry logic with exponential backoff for ClickUp API limits
- **Concurrent Processing**: Configurable concurrency for optimal API utilization
- **RESTful API**: Simple GET endpoint to retrieve cached export data
- **Docker Support**: Full containerized deployment with development and production configurations
- **Monitoring**: Flower integration for Celery task monitoring

## Architecture

```
┌─────────────────┐    ┌──────────────┐    ┌─────────────────┐
│   ClickUp API   │◄───│   Exporter   │───►│   Redis Cache   │
└─────────────────┘    └──────────────┘    └─────────────────┘
                              │
                              ▼
                       ┌──────────────┐
                       │   REST API   │
                       └──────────────┘
```

### Key Components

- **Django Backend**: RESTful API server with gzip compression
- **Nginx**: Reverse proxy and load balancer
- **Celery Worker**: Background task processing
- **Celery Beat**: Task scheduling
- **Redis**: Caching and message broker
- **Flower**: Task monitoring dashboard
- **Redis Insight**: Redis database monitoring

## Quick Start

### Prerequisites

- Docker and Docker Compose
- ClickUp API token and team ID
- Environment variables (see Configuration)

### Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd clickup_exporter
   ```

2. **Environment Setup**
   Create a `.env` file with required configuration:
   ```env
   CLICKUP_TOKEN=pk_your_token_here
   CLICKUP_TEAM_ID=your_team_id
   API_AUTH_TOKEN=your_api_auth_token
   DJANGO_PORT=8000
   FLOWER_USERNAME=admin
   FLOWER_PASSWORD=your_password
   ```

3. **Start the Application**
   ```bash
   make fresh_start
   ```

This will build and start all services including the Django backend, Celery worker, scheduler, and Flower monitoring.

### Development

For subsequent runs, use:
```bash
make start
```

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `CLICKUP_TOKEN` | ClickUp API token | Required |
| `CLICKUP_TEAM_ID` | ClickUp team/workspace ID | Required |
| `API_AUTH_TOKEN` | Bearer token for API authentication | Required |
| `CONCURRENCY` | Number of concurrent API requests | 2 |
| `MAX_RETRIES` | Maximum retry attempts for failed requests | 7 |
| `INITIAL_BACKOFF` | Initial backoff delay (seconds) | 3.0 |
| `REDIS_LOCK_TTL` | Redis lock timeout (seconds) | 1800 |
| `KEEP_LAST_N_EXPORTS` | Number of export versions to retain | 7 |

### ClickUp API Setup

1. **Get API Token**:
   - Go to ClickUp Settings → Apps
   - Generate a new API token
   - Copy the token starting with `pk_`

2. **Find Team ID**:
   - Use ClickUp API: `GET https://api.clickup.com/api/v2/team`
   - Or extract from ClickUp URLs in your workspace

## API Usage

### Export Endpoint

**GET** `localhost/api/v1/export/`

Returns the latest cached export data from ClickUp with gzip compression support.

**Headers:**
```
Authorization: Bearer <your-api-auth-token>
Accept-Encoding: gzip, deflate, br
Cache-Control: no-cache
```

## Development

### Available Commands

```bash
# Development
make fresh_start # Rebuild and start anew
make start       # Start containers
make down        # Stop all services and orphan containers
make shell       # Django shell access
make lint        # Run code linting

# Utilities
make purge       # Remove all containers and volumes
```

### Monitoring

Access monitoring dashboards:
- **Flower**: http://flower.localhost (Celery task monitoring)
- **Redis Insight**: http://redis.localhost (Redis dashboard)

## Data Processing

### Export Process

1. **Scheduled Trigger**: Celery beat triggers export every 5 hours
2. **Data Fetching**: Concurrent API calls to ClickUp for:
   - Workspace spaces and lists
   - Tasks with pagination
   - Time entries for all team members
   - Time-in-status data
3. **Data Enrichment**: Tasks are enhanced with:
   - Time tracking summaries
   - Status duration analytics
   - Space/list metadata
4. **Caching**: Processed data stored in Redis with versioning
5. **API Serving**: Cached data served via REST endpoint

### Performance Features

- **Concurrent Processing**: Configurable async HTTP requests
- **Smart Pagination**: Handles ClickUp's pagination automatically
- **Rate Limit Handling**: Exponential backoff with retry logic
- **Memory Efficiency**: Streaming data processing
- **Cache Versioning**: Daily cache versions with automatic cleanup

## Contributing

1. Follow the existing code style (enforced by Ruff)
2. Test changes with `make lint`
3. Document new features and configuration options
4. Ensure Docker builds work correctly

## License

See [LICENSE](LICENSE) file for details.

---

For support or questions, please refer to the project documentation or contact the maintainers.