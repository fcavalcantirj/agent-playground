"""Shared test fixtures for Phase B Stripe webhook integration tests.

Phase B Plan B-stripe-06 — keeps the ``sign_webhook_payload`` HMAC helper
+ the 7 signed-payload JSON envelopes alongside the test code that
consumes them. The leading underscore mirrors ``tests/_spikes/`` —
fixture-only directories that pytest does not collect.
"""
