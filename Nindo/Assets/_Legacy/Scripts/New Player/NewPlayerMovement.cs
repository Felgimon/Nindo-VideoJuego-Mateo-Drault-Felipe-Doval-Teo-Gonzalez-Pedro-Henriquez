using System.Collections;
using System.Collections.Generic;
using UnityEngine;

public class NewPlayerMovement : MonoBehaviour
{
    [SerializeField] private float speed = 3f;
    [SerializeField] private float rotationSpeed = 1.0f;
    [SerializeField] private float maxRiseSpeed = 1;
    [SerializeField] private float maxFallSpeed = 20;
    [SerializeField] private Rigidbody playerRB;
    [SerializeField] private Animator anim;
    [SerializeField] private LockOnTarget lockOnTarget;
    [SerializeField] private PlayerDash playerDash;
    private Vector3 forward, right;

    public Vector3 MoveDirection
    {
        get
        {
            float horizontalInput = Input.GetAxis("Horizontal");
            float verticalInput = Input.GetAxis("Vertical");
            Vector3 direction = horizontalInput * right + verticalInput * forward;
            return direction.normalized;
        }
    }

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
        //Debug.Log($"Horizontal={Input.GetAxis("Horizontal")}, Vertical={Input.GetAxis("Vertical")}");

        float horizontalInput = Input.GetAxis("Horizontal");
        float verticalInput = Input.GetAxis("Vertical");
        Vector3 direction = horizontalInput * right + verticalInput * forward;
        if (direction != Vector3.zero && !anim.GetCurrentAnimatorStateInfo(0).IsName("Stunned") && !anim.GetCurrentAnimatorStateInfo(0).IsName("Attacking") && !anim.GetCurrentAnimatorStateInfo(0).IsName("Parrying") && !playerDash.isDashing)
        {
            anim.SetBool("isRunning", true);
            transform.position += direction * speed * Time.deltaTime;
            if (!lockOnTarget.isLocked)
            {
                Quaternion Target = Quaternion.LookRotation(direction);
                transform.rotation = Quaternion.Slerp(transform.rotation, Target, rotationSpeed * Time.deltaTime);
            }
        }
        if (direction == Vector3.zero)
        {
            anim.SetBool("isRunning", false);
        }
    }
    void FixedUpdate()
    {
        Vector3 vel = playerRB.velocity;
        vel.y = Mathf.Clamp(vel.y, -maxFallSpeed, maxRiseSpeed);
        playerRB.velocity = vel;
    }
}
