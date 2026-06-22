package com.routeresilience.gateway.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

/** CORS for the vanilla dashboard when it's served separately from the gateway (Live Server,
 *  the compute service on :8000, a static host, etc.). GET for the read-only analysis, POST so
 *  the Scale Lab can submit async jobs. Any localhost port is allowed — this is a dev gateway. */
@Configuration
public class WebConfig implements WebMvcConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedOriginPatterns("http://localhost:*", "http://127.0.0.1:*")
                .allowedMethods("GET", "POST");
    }
}
