package com.routeresilience.gateway.config;

import com.github.benmanes.caffeine.cache.Caffeine;
import org.springframework.cache.CacheManager;
import org.springframework.cache.caffeine.CaffeineCacheManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.time.Duration;

/**
 * In-process result cache. Criticality is static until the graph or scenario changes, so it
 * is exactly the kind of expensive-but-stable result a cache is made for (plan §9).
 *
 * <p>Caffeine keeps this dependency-free for local runs. In a clustered deployment you'd swap
 * in the Redis profile so the cache is shared across gateway instances and survives a
 * restart — same {@code @Cacheable} annotations, different manager.
 */
@Configuration
public class CacheConfig {

    public static final String CRITICALITY = "criticality";
    public static final String ROBUSTNESS = "robustness";

    @Bean
    public CacheManager cacheManager() {
        var manager = new CaffeineCacheManager(CRITICALITY, ROBUSTNESS);
        manager.setCaffeine(Caffeine.newBuilder()
                .maximumSize(64)
                .expireAfterWrite(Duration.ofHours(6))   // re-validate twice a day; cities don't change fast
                .recordStats());
        return manager;
    }
}
