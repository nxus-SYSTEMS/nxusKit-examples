; Pallet-door dimensional feasibility guardrails.

(deftemplate clearance
  (slot pallet-width)
  (slot door-width)
  (slot load-state))

(deftemplate action
  (slot id)
  (slot movement))

(deftemplate guardrail-finding
  (slot status)
  (slot rule-id)
  (slot severity)
  (slot message))

(defrule door-clearance-too-small
  (clearance
    (pallet-width ?p)
    (door-width ?d&:(< ?d ?p)))
  =>
  (assert
    (guardrail-finding
      (status fail)
      (rule-id door-clearance-too-small)
      (severity error)
      (message "The loaded pallet is wider than the door opening."))))

(defrule tilt-unsafe-for-load
  (clearance
    (load-state loaded))
  (action
    (id angle-and-push))
  =>
  (assert
    (guardrail-finding
      (status fail)
      (rule-id tilt-unsafe-for-load)
      (severity error)
      (message "Tilting or forcing a loaded pallet is outside the safe handling rule."))))
