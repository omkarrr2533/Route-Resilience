package com.routeresilience.gateway.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * Sizing for the async job pool. A bounded worker count and a bounded queue are the whole point
 * (plan §7): concurrent analysis requests queue rather than spawning unbounded threads and
 * OOM-ing the box. Overridable via {@code jobs.*} in application.yml.
 */
@ConfigurationProperties(prefix = "jobs")
public record JobsProperties(Integer workers, Integer queueCapacity) {

    public JobsProperties {
        if (workers == null || workers < 1) workers = 2;
        if (queueCapacity == null || queueCapacity < 1) queueCapacity = 32;
    }
}
