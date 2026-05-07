; Cold-chain carrier eligibility and audit guardrails.

(deftemplate carrier
  (slot id)
  (slot refrigerated)
  (slot temperature-logging)
  (slot certified))

(deftemplate custody
  (slot handoff-record)
  (slot audit-record))

(deftemplate guardrail-finding
  (slot status)
  (slot rule-id)
  (slot severity)
  (slot message))

(defrule carrier-not-certified
  (carrier
    (id cheap-courier)
    (certified false))
  =>
  (assert
    (guardrail-finding
      (status fail)
      (rule-id carrier-not-certified)
      (severity error)
      (message "The selected carrier is not certified for refrigerated medical shipment."))))

(defrule temperature-audit-missing
  (carrier
    (temperature-logging false))
  (custody
    (handoff-record false))
  =>
  (assert
    (guardrail-finding
      (status fail)
      (rule-id temperature-audit-missing)
      (severity error)
      (message "The plan lacks temperature monitoring and custody handoff evidence."))))
