using System.Collections;
using System.Collections.Generic;
using UnityEngine;

public class PlayerDash : MonoBehaviour
{
    public float attackDashSpeed = 5f;//velocidad del dash
    public float attackDashTime = 0.15f;//duración del dash en segundos
    public bool isDashing = false;
    [SerializeField] private NewPlayerMovement playerMovement;
    [SerializeField] private Rigidbody playerRB;
    private Vector3 dashVelocity;
    [SerializeField] private Animator invisible;
    [SerializeField] private Animator animator;

    [SerializeField] private ManaBar manaBar;
    [SerializeField] private MeshTrail trail;
    [SerializeField] private float dashManaCost = 20f;

    // Start is called before the first frame update
    void Start()
    {
        
    }

    // Update is called once per frame
    void Update()
    {
        if (Input.GetKeyDown(KeyCode.LeftShift) & manaBar.currentMana >= dashManaCost) 
        {
            trail.StartCoroutine(trail.ActivateTrail(trail.activeTime));
            DoAttackDash();
            animator.SetTrigger("Dash");
            invisible.SetTrigger("Dash");
            SoundManager.PlaySound(SoundType.DASH, 0.5f);
        }
    }

    private void FixedUpdate()
    {
        if (isDashing)
        {
            playerRB.velocity = dashVelocity;
        }
    }


    public void DoAttackDash()
    {
        StartCoroutine(AttackDash());
    }



    private IEnumerator AttackDash()
    {
        manaBar.gastarMana(dashManaCost);
        isDashing = true;

        Vector3 dashDirection = playerMovement.MoveDirection;
        if (dashDirection == Vector3.zero)
            dashDirection = transform.forward;

        dashVelocity = dashDirection.normalized * attackDashSpeed;

        yield return new WaitForSeconds(attackDashTime);
        // Al terminar, para el dash
        playerRB.velocity = Vector3.zero;
        isDashing = false;
    }
}
