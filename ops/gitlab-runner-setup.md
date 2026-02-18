# GitLab URL and Artifacts Setup

## 1) Correct external URL (no container-id links)
Set the public URL in GitLab itself:

```ruby
# /etc/gitlab/gitlab.rb
external_url "https://gitlab.your-domain.ru"
```

Then apply:

```bash
sudo gitlab-ctl reconfigure
sudo gitlab-ctl restart
```

For Runner, verify it points to the same external address:

```toml
# /etc/gitlab-runner/config.toml
[[runners]]
  url = "https://gitlab.your-domain.ru/"
```

## 2) Fix artifacts 500 errors (bind mount ownership issue)
Most stable option: store artifacts in a Docker `volume` (not bind mount).

Example (`docker-compose.yml`) for GitLab container:

```yaml
services:
  gitlab:
    image: gitlab/gitlab-ce:latest
    volumes:
      - gitlab_config:/etc/gitlab
      - gitlab_logs:/var/log/gitlab
      - gitlab_data:/var/opt/gitlab
      - gitlab_artifacts:/var/opt/gitlab/gitlab-rails/shared/artifacts

volumes:
  gitlab_config:
  gitlab_logs:
  gitlab_data:
  gitlab_artifacts:
```

If artifacts were already in bind mount, copy them once into volume:

```bash
# inside host
docker run --rm \
  -v /old/bind/artifacts:/from \
  -v gitlab_artifacts:/to \
  alpine sh -c "cp -a /from/. /to/"
```

Then ensure ownership in GitLab container:

```bash
docker exec -it <gitlab_container> chown -R git:git /var/opt/gitlab/gitlab-rails/shared/artifacts
```

For Omnibus image it is usually UID/GID `998:998`:

```bash
docker exec -it <gitlab_container> chown -R 998:998 /var/opt/gitlab/gitlab-rails/shared/artifacts
```

## 3) Project-level URL for app links during CI
`.gitlab-ci.yml` already sets:

```yaml
SITE_BASE_URL: "$CI_PROJECT_URL"
```

This prevents app-generated links from using container-internal hosts.
