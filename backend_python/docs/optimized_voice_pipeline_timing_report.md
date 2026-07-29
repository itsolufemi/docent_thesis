# Optimised TRP full voice-pipeline timing report

Date: 29 July 2026

Branch: `voice-pipeline-timing-test`

## Objective

Measure the actual production voice request path after replacing the original
TRP request with structured Gemma 4 streaming:

```text
voice onset
-> VAD speech confirmation
-> PCM streaming
-> 600 ms silence boundary
-> Faster Whisper
-> optimised streamed TRP
-> turn finalisation
-> utterance classifier
-> retrieval
-> streamed assistant response
```

The endpoint for this report is the completed textual query response. Browser
TTS synthesis and playback are outside the original timing harness and are not
included.

## Configuration

- Voice fixture: `tmp/latency/voice_request.wav`
- Spoken duration: 1.32 seconds
- Transcript in every run: `Tell me about the swing.`
- VAD speech-end threshold: 600 milliseconds
- TRP model: value configured by `OLLAMA_TRP_MODEL` (`gemma4:cloud` during
  this test)
- TRP streaming: enabled
- TRP thinking: disabled
- TRP format: structured JSON schema
- TRP generation limit: 160 tokens
- TRP early return: first complete schema-valid `TRPPrediction`
- Runs: three consecutive traces using one backend process

The first run includes cold service effects. Runs two and three reused the
loaded Whisper model and in-memory vector index.

## Individual results

| Measurement | Run 1 | Run 2 | Run 3 |
|---|---:|---:|---:|
| Voice plus VAD boundary | 1.9417 s | 1.9492 s | 1.9446 s |
| Whisper interval | 2.6163 s | 0.6525 s | 0.5949 s |
| Turn event sent | 4.5596 s | 2.6036 s | 2.5415 s |
| Optimised TRP and turn evaluation | 1.1513 s | 0.8868 s | 0.9457 s |
| Turn finalised, cumulative | 5.7109 s | 3.4904 s | 3.4872 s |
| Classifier interval | 1.3963 s | 4.8504 s | 1.7893 s |
| Classifier complete, cumulative | 7.1072 s | 8.3408 s | 5.2765 s |
| Vector retrieval | 3.7476 s | 0.4051 s | 0.3041 s |
| Query start to first text delta | 16.1754 s | 1.5677 s | 1.9368 s |
| First assistant text, cumulative | 23.2829 s | 9.9087 s | 7.2135 s |
| Full query complete, cumulative | 23.5022 s | 10.5291 s | 7.6326 s |

Run 1 made two invalid `create_conversation_branch` tool calls. Those extra
model rounds increased response-generation time to 12.6280 seconds and made
the run a clear behavioural outlier.

Run 2 had no tool calls, but its classifier request took 4.8504 seconds,
showing a separate cloud-latency spike.

Run 3 had no tool calls and no major cloud outlier. It completed the entire
textual voice request in 7.6326 seconds, with the first assistant text visible
after 7.2135 seconds.

## Three-run medians

| Measurement | Median |
|---|---:|
| Whisper interval | 0.6525 s |
| Optimised TRP and turn evaluation | **0.9457 s** |
| Turn finalised from voice onset | **3.4904 s** |
| Classifier interval | 1.7893 s |
| Classifier boundary from voice onset | 7.1072 s |
| Retrieval interval | 0.4075 s |
| Query start to first assistant text | 1.9368 s |
| First assistant text from voice onset | **9.9087 s** |
| Full assistant response from voice onset | **10.5291 s** |

Component medians are calculated independently and therefore should not be
summed to reconstruct one synthetic run.

## Comparison with the original full voice-pipeline traces

The original committed experiment used the same fixture and timing harness.
The comparison below uses the median of its three traces and the median of the
three new traces.

| Boundary or stage | Original median | Optimised median | Change |
|---|---:|---:|---:|
| Whisper interval | 1.7768 s | 0.6525 s | -1.1243 s |
| TRP and turn evaluation | 1.3408 s | **0.9457 s** | **-0.3951 s (-29.5%)** |
| Turn finalised from voice onset | 5.0680 s | **3.4904 s** | **-1.5776 s (-31.1%)** |
| Classifier interval | 3.2314 s | 1.7893 s | -1.4421 s |
| Classifier boundary | 7.1233 s | 7.1072 s | -0.0161 s |
| Query start to first text | 2.9542 s | 1.9368 s | -1.0174 s |
| First assistant text | 10.0776 s | **9.9087 s** | **-0.1689 s (-1.7%)** |
| Full query complete | 10.5214 s | **10.5291 s** | +0.0077 s |

The most direct result is that the new production TRP reduced the actual
median TRP/turn-evaluation interval by 395 milliseconds, or 29.5%. Turn
finalisation occurred 1.58 seconds earlier in the new traces, although part of
that larger difference came from a faster warmed Whisper measurement.

The median full response did not improve: 10.5291 seconds versus 10.5214
seconds is effectively identical. The saved TRP time was obscured by variance
in later cloud stages, especially classification and tool-aware response
generation.

The distribution widened:

- original full-query range: 10.2652-14.2227 seconds;
- optimised full-query range: 7.6326-23.5022 seconds.

The fastest new trace beat the fastest original trace by 2.6326 seconds, but
the invalid tool-call sequence made the slowest new trace substantially worse.

## Functional observation

All three runs correctly:

- transcribed the fixture;
- returned `finalise_turn`;
- classified it as a retrieval-backed `response_request`;
- began and completed a streamed assistant response.

However, all three responses reported that no information about The Swing was
available. No sources survived retrieval, even though the classifier supplied
`the swing` as a candidate subject. Run 1 then attempted two malformed
conversation-branch tool calls.

This is separate from the TRP optimisation, but it means the full flow passed
transport and timing validation while failing the intended factual-answer
outcome. Retrieval subject propagation and the branch-tool argument contract
should be investigated independently.

## Conclusion

The optimized TRP is working in the real voice pipeline and reduced its own
median stage latency from 1.3408 to 0.9457 seconds. The best complete trace
finished in 7.6326 seconds.

The three-run median from voice onset to complete assistant text remained
approximately 10.53 seconds because the pipeline's dominant variability has
moved downstream:

1. cloud utterance classification;
2. tool-aware main-model generation;
3. invalid or unnecessary tool-call retries;
4. cold Whisper and embedding initialization.

Further whole-pipeline latency work should therefore focus on classifier tail
latency and preventing invalid conversation-tree tool rounds. The TRP change
should be retained: it is faster, accurate, and was not the cause of the slow
outlier.
