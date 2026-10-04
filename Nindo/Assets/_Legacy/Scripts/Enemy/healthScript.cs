using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UI;

public class healthScript : MonoBehaviour
{
    [SerializeField] private Transform target;
    [SerializeField] private Vector3 offSet;
    [SerializeField] private Image redBar;
    [SerializeField] private Image killBar;
    [SerializeField] private EnemyBeingDamaged enemyBeingDamaged;

    // Start is called before the first frame update
    void Start()
    {
        killBar.fillAmount = enemyBeingDamaged.finisherThreshold / enemyBeingDamaged.maxHealthAmount;
    }

    // Update is called once per frame
    void Update()
    {
        transform.position = target.position + offSet;
    }
    public void UpdateHealthBar(float maxHealthAmount, float health)
    {
        redBar.fillAmount = health/ maxHealthAmount;
        //Debug.Log(maxHealthAmount);
        //Debug.Log(health);

    }
}
