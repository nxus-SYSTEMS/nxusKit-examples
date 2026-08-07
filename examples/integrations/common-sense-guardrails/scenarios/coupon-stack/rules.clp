; Coupon stack policy guardrails.

(deftemplate promotion-action
  (slot id)
  (multislot discounts)
  (slot free-shipping)
  (slot non-stackable-count)
  (slot margin-after-stack))

(deftemplate guardrail-finding
  (slot status)
  (slot rule-id)
  (slot severity)
  (slot message))

(defrule non-stackable-discount-conflict
  (promotion-action
    (non-stackable-count ?count&:(> ?count 1)))
  =>
  (assert
    (guardrail-finding
      (status fail)
      (rule-id non-stackable-discount-conflict)
      (severity error)
      (message "The recommendation combines non-stackable promotion families."))))

(defrule margin-floor-breach
  (promotion-action
    (margin-after-stack ?m&:(< ?m 20)))
  =>
  (assert
    (guardrail-finding
      (status fail)
      (rule-id margin-floor-breach)
      (severity error)
      (message "The stacked promotion drives the clearance item below the allowed margin floor."))))
