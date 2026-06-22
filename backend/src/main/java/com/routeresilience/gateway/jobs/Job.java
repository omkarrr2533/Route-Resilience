package com.routeresilience.gateway.jobs;

import java.time.Instant;

/**
 * A single async job and its live state. One worker thread mutates it while HTTP threads read
 * it for status polls, so every mutable field is {@code volatile} — coarse but correct for this
 * single-writer/many-reader shape; nothing here needs compound atomicity.
 */
public class Job {

    private final String id;
    private final String type;
    private final String key;
    private final Instant createdAt = Instant.now();

    private volatile JobStatus status = JobStatus.QUEUED;
    private volatile double progress = 0.0;
    private volatile String message = "queued";
    private volatile Instant startedAt;
    private volatile Instant finishedAt;
    private volatile Object result;
    private volatile String error;

    // live progress detail
    private volatile long samplesDone;
    private volatile int targetSamples;
    private volatile double currentEpsilon = 1.0;
    private volatile double targetEpsilon;
    private volatile int batches;

    public Job(String id, String type, String key) {
        this.id = id;
        this.type = type;
        this.key = key;
    }

    public void running() {
        this.status = JobStatus.RUNNING;
        this.startedAt = Instant.now();
        this.message = "running";
    }

    public void advance(double progress, long samplesDone, int targetSamples,
                        double currentEpsilon, double targetEpsilon, int batches) {
        this.progress = progress;
        this.samplesDone = samplesDone;
        this.targetSamples = targetSamples;
        this.currentEpsilon = currentEpsilon;
        this.targetEpsilon = targetEpsilon;
        this.batches = batches;
        this.message = "sampling — " + samplesDone + " sources, ε≈" + round(currentEpsilon);
    }

    public void succeed(Object result, String message) {
        this.result = result;
        this.progress = 1.0;
        this.message = message;
        this.finishedAt = Instant.now();
        this.status = JobStatus.SUCCEEDED;
    }

    public void fail(String error) {
        this.error = error;
        this.message = "failed";
        this.finishedAt = Instant.now();
        this.status = JobStatus.FAILED;
    }

    public JobStatus status() {
        return status;
    }

    public String id() {
        return id;
    }

    public JobView toView() {
        JobView.Progress detail = batches > 0
                ? new JobView.Progress(samplesDone, targetSamples,
                        round(currentEpsilon), round(targetEpsilon), batches)
                : null;
        return new JobView(id, type, status.name().toLowerCase(), round(progress), message,
                createdAt, startedAt, finishedAt, detail, result, error);
    }

    private static double round(double x) {
        return Math.round(x * 1e6) / 1e6;
    }
}
