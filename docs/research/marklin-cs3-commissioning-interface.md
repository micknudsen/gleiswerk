# Märklin CS3+ commissioning-interface research

- Researched: 2026-08-15
- Scope: whether a Gleiswerk commissioning tool can read configured turnout
  channels and treat a command response as an acknowledgement.

## Finding

Märklin publishes a browser-oriented **operator web interface** for the CS3,
not a documented, stable, machine-consumable API for configuration inventory
or command acknowledgements. The public CS3 short tutorial says that the web
interface is reached by entering the CS3 IP address on the same network and
that it supports direct control of switching items; it does not specify HTTP
endpoints, response schemas, authentication, configuration export formats, or
an acknowledgement contract. [Märklin CS3 Short Tutorial, pp. 1, 25–26](https://streaming.maerklin.de/public-media/anleitungen/CS3_Manual_EN_final-lo.pdf)

This is an inference from the scope and content of the vendor documentation,
not a claim that an undocumented interface does not exist. It means Gleiswerk
must not represent a discovered private web endpoint, a UI state change, or a
successful HTTP response as a supported Märklin API or as physical turnout
evidence.

## What the official documentation does establish

- The CS3+ (60216) has a direct S88 connection; the non-plus CS3 requires a
  Link S88 for feedback modules. [Märklin CS3 Short Tutorial, pp. 1–2](https://streaming.maerklin.de/public-media/anleitungen/CS3_Manual_EN_final-lo.pdf)
- Märklin specifies S88 modules as inputs for contact generators. That is
  generic contact feedback, not inherent turnout-end-position feedback; a
  turnout's position can be observed only when an independently wired contact
  is deliberately bound to that meaning. [Märklin S88 feedback module
  60881](https://www.marklin.com/products/details/article/60881);
  [Märklin Link S88 60883](https://www.marklin.com/products/details/article/60883)
- The controller has a LAN connection to a router and provides a browser web
  interface. The manual requires CS3 software 1.3.3 or later and says the
  accessing device must be on the same network; Internet access is not
  necessary. [Märklin CS3 Short Tutorial, p. 25](https://streaming.maerklin.de/public-media/anleitungen/CS3_Manual_EN_final-lo.pdf)
- The web UI can perform direct control, including switching items. Changes
  are reflected to other control devices, and commands are processed in the
  order received. This describes operator control ordering, not a per-command
  delivery or actuator-success acknowledgement. [Märklin CS3 Short Tutorial,
  pp. 25–26](https://streaming.maerklin.de/public-media/anleitungen/CS3_Manual_EN_final-lo.pdf)
- Solenoid items, including turnouts, signals, and contacts, are user-configured
  CS3 items. The product page advertises control capacity but does not promise
  feedback of their physical state. [Märklin CS3 Short Tutorial, pp. 5,
  13–15](https://streaming.maerklin.de/public-media/anleitungen/CS3_Manual_EN_final-lo.pdf);
  [CS3 product page](https://www.marklin.com/products/details/article/60226)
- Märklin continually develops CS3 software and provides updates. A firmware
  change can therefore change undocumented behavior and must invalidate a
  commissioning integration until it is retested. [Märklin CS3 Short Tutorial,
  p. 24](https://streaming.maerklin.de/public-media/anleitungen/CS3_Manual_EN_final-lo.pdf)

## Integration decision and safe constraints

1. **No stable public API claim.** Treat configuration reading and any
   command response as a firmware-pinned, adapter-private integration until
   Märklin publishes a versioned machine API with schemas and acknowledgement
   semantics.
2. **Read-only configuration comparison.** The adapter may obtain the CS3
   configuration only to compare each binding-declared command channel with
   the controller's configured item. It must not create, edit, delete, or
   auto-repair CS3 items.
3. **Pin and attest the result.** Record CS3 model, firmware version, endpoint,
   the exact acquisition method/version, and a canonical hash of the parsed
   configuration snapshot in the commissioning record. Reject an unknown
   firmware, missing/ambiguous item, unsupported protocol/address shape, or
   parse failure.
4. **Fail closed on interface drift.** Characterization tests must run against
   the commissioned firmware and fixtures captured from it. Any firmware,
   endpoint, parser, response-shape, or configuration change requires a new
   successful commissioning run; no cached configuration may authorize
   movement.
5. **Bound command acknowledgement precisely.** A successful adapter-level
   response may mean only that the command station accepted the requested
   channel/position. Time out, malformed/ambiguous response, disconnect, or a
   superseding command makes the corresponding assumed assertion unavailable.
   It never proves coil energization, mechanical throw, lock, or continued
   turnout position.
6. **Keep the trust boundary explicit.** After the configured settling delay,
   the accepted command may form the `assumed-after-delay` assertion adopted
   by ADR 0016. Its provenance must remain distinct from sensor evidence; fresh
   S88 occupancy remains independently required. The controller and the
   commissioning host belong on the isolated wired LAN described in the
   installation binding.

## Consequence for the next implementation

The next issue should define an adapter seam with two deliberately narrow
operations: `read_configured_command_channels()` and
`command_and_confirm_acceptance()`. The safety core should receive only a
validated configuration-match result and a bounded assumed-position assertion.
It should not depend on CS3 HTTP paths, UI markup, network packet shapes, or
the word “acknowledgement” having a physical meaning.
