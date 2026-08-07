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
    (certified false))
  =>
  (assert
    (guardrail-finding
      (status fail)
      (rule-id carrier-not-certified)
      (severity error)
      (message "The selected carrier is not certified for refrigerated medical shipment."))))

(defrule carrier-not-refrigerated
  (carrier
    (refrigerated false))
  =>
  (assert
    (guardrail-finding
      (status fail)
      (rule-id carrier-not-refrigerated)
      (severity error)
      (message "The selected carrier does not provide refrigerated service."))))

(defrule temperature-logging-missing
  (carrier
    (temperature-logging false))
  =>
  (assert
    (guardrail-finding
      (status fail)
      (rule-id temperature-logging-missing)
      (severity error)
      (message "The selected carrier does not provide temperature logging."))))

(defrule custody-handoff-missing
  (custody
    (handoff-record false))
  =>
  (assert
    (guardrail-finding
      (status fail)
      (rule-id custody-handoff-missing)
      (severity error)
      (message "The plan lacks documented custody handoff evidence."))))

(defrule temperature-audit-missing
  (custody
    (audit-record false))
  =>
  (assert
    (guardrail-finding
      (status fail)
      (rule-id temperature-audit-missing)
      (severity error)
      (message "The plan lacks required temperature-monitoring evidence."))))
