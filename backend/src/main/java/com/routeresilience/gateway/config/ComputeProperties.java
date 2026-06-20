package com.routeresilience.gateway.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

import java.time.Duration;

/**
 * Where the compute service lives and how patient we are with it. Bound from the
 * {@code compute.*} keys in application.yml (overridable by env var, which is how
 * docker-compose points us at the container instead of localhost).
 */
@ConfigurationProperties(prefix = "compute")
public record ComputeProperties(
        String baseUrl,
        Duration connectTimeout,
        Duration readTimeout
) {
    public ComputeProperties {
        if (baseUrl == null || baseUrl.isBlank()) {
            baseUrl = "http://localhost:8000";
        }
        if (connectTimeout == null) connectTimeout = Duration.ofSeconds(2);
        // Generous: an uncached city-scale betweenness run is genuinely slow. The cache is
        // what keeps the *typical* request fast; this timeout is the cold-path ceiling.
        if (readTimeout == null) readTimeout = Duration.ofMinutes(2);
    }
}
