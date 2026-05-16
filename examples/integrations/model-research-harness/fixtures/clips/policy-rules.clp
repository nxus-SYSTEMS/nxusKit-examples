; Public-safe CLIPS policy sketch for model research harness outputs.
(deftemplate model-output
  (slot label)
  (slot confidence))

(deftemplate policy-finding
  (slot rule-id)
  (slot severity)
  (slot message))

(defrule block-unknown-label
  (model-output (label unknown))
  =>
  (assert (policy-finding
    (rule-id no-unknown-label)
    (severity high)
    (message "Model returned an unknown label"))))
