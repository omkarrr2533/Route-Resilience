package com.routeresilience.gateway.jobs;

import com.routeresilience.gateway.config.JobsProperties;
import com.routeresilience.gateway.service.ComputeClient;
import jakarta.annotation.PreDestroy;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

/**
 * The async job layer — the gateway's reason for existing beyond caching (plan §3, §11).
 *
 * <p>Long analyses run on a <em>bounded</em> worker pool fed by a bounded queue, so a burst of
 * requests degrades into waiting rather than into an out-of-memory crash. Jobs are deduplicated
 * by an idempotency key: re-submitting an identical analysis returns the in-flight (or finished)
 * job instead of recomputing it — the same instinct as the result cache, one level up.
 *
 * <p>The registry is in-memory, which is honest about what this is: a single-instance
 * orchestrator. The clustered version moves the registry and the queue into Redis (already a
 * dependency) so jobs survive a restart and fan out across gateways — same control flow.
 */
@Service
public class JobService {

    private final ComputeClient compute;
    private final ThreadPoolExecutor pool;
    private final Map<String, Job> jobs = new ConcurrentHashMap<>();
    private final Map<String, String> byKey = new ConcurrentHashMap<>();

    public JobService(ComputeClient compute, JobsProperties props) {
        this.compute = compute;
        this.pool = new ThreadPoolExecutor(
                props.workers(), props.workers(),
                0L, TimeUnit.MILLISECONDS,
                new LinkedBlockingQueue<>(props.queueCapacity()),
                worker(),
                new ThreadPoolExecutor.AbortPolicy());   // a full queue rejects loudly, not silently
    }

    public Job submitApprox(ApproxBetweennessRequest req) {
        // Idempotency: an identical request already running or done is the answer — don't redo it.
        Job existing = lookup(req.key());
        if (existing != null) {
            return existing;
        }

        String id = UUID.randomUUID().toString().substring(0, 8);
        Job job = new Job(id, "approx-betweenness", req.key());
        jobs.put(id, job);
        byKey.put(req.key(), id);

        try {
            pool.execute(new ApproxBetweennessJob(job, req, compute));
        } catch (RejectedExecutionException ex) {
            job.fail("the gateway is at capacity — the job queue is full, retry shortly");
        }
        return job;
    }

    public Optional<Job> get(String id) {
        return Optional.ofNullable(jobs.get(id));
    }

    public List<Job> all() {
        return new ArrayList<>(jobs.values());
    }

    private Job lookup(String key) {
        String id = byKey.get(key);
        if (id == null) {
            return null;
        }
        Job job = jobs.get(id);
        // A failed job shouldn't pin the key — let a resubmit try again.
        return (job != null && job.status() != JobStatus.FAILED) ? job : null;
    }

    private java.util.concurrent.ThreadFactory worker() {
        return r -> {
            Thread t = new Thread(r, "job-worker");
            t.setDaemon(true);
            return t;
        };
    }

    @PreDestroy
    public void shutdown() {
        pool.shutdownNow();
    }
}
