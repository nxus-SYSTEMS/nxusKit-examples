; Car wash object-presence guardrail.

(deftemplate required-object
  (slot object)
  (slot required-location)
  (slot current-location)
  (slot present-at-required-location))

(deftemplate moved-object
  (slot action-id)
  (slot object)
  (slot from)
  (slot to))

(deftemplate guardrail-finding
  (slot status)
  (slot rule-id)
  (slot severity)
  (slot message))

(defrule car-required-at-wash
  (required-object
    (object car)
    (required-location car_wash)
    (current-location ?where)
    (present-at-required-location false))
  (not
    (moved-object
      (object car)
      (to car_wash)))
  =>
  (assert
    (guardrail-finding
      (status fail)
      (rule-id car-required-at-wash)
      (severity error)
      (message "The selected action does not put the car at the wash location."))))
