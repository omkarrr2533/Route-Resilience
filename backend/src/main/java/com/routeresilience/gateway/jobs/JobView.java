package com.routeresilience.gateway.jobs;

import java.time.Instant;

/**
 * The serialized face of a {@link Job} — what the browser polls. {@code detail} carries the
 * live progress (sources in, the shrinking ε); {@code result} is null until the job succeeds.
 */
public record JobView(
        String id, String type, String status, double progress, String message,
        Instant createdAt, Instant startedAt, Instant finishedAt,
        Progress detail, Object result, String error) {

    public record Progress(
            long samplesDone, int targetSamples,
            double currentEpsilon, double targetEpsilon, int batches) {}
}
