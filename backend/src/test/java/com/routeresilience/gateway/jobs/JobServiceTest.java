package com.routeresilience.gateway.jobs;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.routeresilience.gateway.config.JobsProperties;
import com.routeresilience.gateway.service.ComputeClient;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.atLeast;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/**
 * Exercises the real aggregation worker against a mocked compute service: the job has to fold
 * the batches into one estimate, drive ε down to the target, rank the segments, and dedupe an
 * identical resubmission.
 */
class JobServiceTest {

    private final ObjectMapper om = new ObjectMapper();

    private JsonNode batch(int samples) throws Exception {
        // a fixed three-edge network; (1,2) is the clear front-runner
        String json = """
            {"edges":[{"u":1,"v":2,"b":0.40},{"u":2,"v":3,"b":0.12},{"u":3,"v":4,"b":0.05}],
             "meta":{"n":46,"m":74,"samples":%d,"seed":0}}
            """.formatted(samples);
        return om.readTree(json);
    }

    private JobService service() throws Exception {
        ComputeClient compute = mock(ComputeClient.class);
        when(compute.sampleBatch(anyString(), anyString(), anyInt(), anyInt()))
                .thenAnswer(inv -> batch(inv.getArgument(2)));   // echo the requested batch size
        return new JobService(compute, new JobsProperties(2, 32));
    }

    @Test
    void aggregatesBatchesUntilTheBoundIsMet() throws Exception {
        JobService svc = service();
        var req = new ApproxBetweennessRequest("sample:koramangala", "length", 0.05, 0.1, 150, 20_000);

        JobView view = await(svc, svc.submitApprox(req).id());

        assertThat(view.status()).isEqualTo("succeeded");
        assertThat(view.detail().currentEpsilon()).isLessThanOrEqualTo(0.05 + 1e-9);

        var result = (ApproxResult) view.result();
        assertThat(result.top().get(0)).extracting(EdgeEstimate::u, EdgeEstimate::v)
                .containsExactly(1, 2);                        // ranking preserved through aggregation
        assertThat(result.meta().samples()).isGreaterThanOrEqualTo(result.meta().m());
        assertThat(result.meta().exactSources()).isEqualTo(46);
    }

    @Test
    void streamsManyBatchesNotOneBigCall() throws Exception {
        ComputeClient compute = mock(ComputeClient.class);
        when(compute.sampleBatch(anyString(), anyString(), anyInt(), anyInt()))
                .thenAnswer(inv -> batch(inv.getArgument(2)));
        JobService svc = new JobService(compute, new JobsProperties(2, 32));

        await(svc, svc.submitApprox(new ApproxBetweennessRequest(
                null, null, 0.05, 0.1, 150, 20_000)).id());

        // target ≈ 1460 sources / 150 per batch ⇒ ~10 batches, i.e. real streaming progress
        verify(compute, atLeast(8)).sampleBatch(anyString(), anyString(), anyInt(), anyInt());
    }

    @Test
    void identicalRequestIsDeduplicated() throws Exception {
        JobService svc = service();
        var req = new ApproxBetweennessRequest("sample:koramangala", "length", 0.05, 0.1, 150, 20_000);

        Job first = svc.submitApprox(req);
        Job second = svc.submitApprox(req);                    // same key → same job, not a recompute
        assertThat(second.id()).isEqualTo(first.id());
    }

    private JobView await(JobService svc, String id) throws InterruptedException {
        for (int i = 0; i < 200; i++) {
            JobView v = svc.get(id).orElseThrow().toView();
            if (v.status().equals("succeeded") || v.status().equals("failed")) {
                return v;
            }
            Thread.sleep(25);
        }
        throw new AssertionError("job " + id + " did not finish in time");
    }
}
