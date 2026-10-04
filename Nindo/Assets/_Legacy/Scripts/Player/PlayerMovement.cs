using System.Collections;
using System.Collections.Generic;
using UnityEngine;

public class PlayerMovement : MonoBehaviour
{
    [SerializeField] private float speed = 3f;
    [SerializeField] private float rotationSpeed = 1.0f;
    [SerializeField] private float maxRiseSpeed = 1;
    [SerializeField] private float maxFallSpeed = 20;
    [SerializeField] private Rigidbody playerRB;
    [SerializeField] private Animator anim;
    [SerializeField] private LockOnTarget lockOnTarget;
    [SerializeField] private PlayerSwordAnimation playerSwordAnimation;
    private Vector3 forward, right;
    void Start()
    {
        forward = Camera.main.transform.forward;
        forward.y = 0;
        forward = Vector3.Normalize(forward);

        right = Camera.main.transform.right;
        right.y = 0;
        right = Vector3.Normalize(right);

    }

    // Update is called once per frame
    void Update()
    {

    }
    void FixedUpdate()
    {
        Vector3 vel = playerRB.velocity;
        vel.y = Mathf.Clamp(vel.y, -maxFallSpeed, maxRiseSpeed);
        playerRB.velocity = vel;
    }
}
